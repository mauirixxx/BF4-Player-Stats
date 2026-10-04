"""Phase 1 single-job detailed collector orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from time import monotonic, sleep
from typing import Sequence
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Engine

from bf4ps.battlelog_detailed import DetailedStatsError, fetch_detailed_stats, normalize_detailed_stats
from bf4ps.collection_jobs import claim_next_job, mark_job_running
from bf4ps.detailed_failure import classify_detailed_failure, persist_detailed_retry_failure
from bf4ps.detailed_persistence import persist_detailed_success
from bf4ps.request_gate import reserve_request_slot


@dataclass(frozen=True)
class CollectorIdentity:
    collector_uuid: UUID
    collector_name: str
    hostname: str
    egress_key: str
    lane: str = "background"


@dataclass(frozen=True)
class CollectedJob:
    job_id: int
    soldier_id: int
    persona_id: int
    platform: str
    history_appended: bool
    duration_ms: int


@dataclass(frozen=True)
class FailedJob:
    job_id: int
    soldier_id: int
    persona_id: int
    platform: str
    error_class: str
    http_status: int | None
    retry_after_seconds: int
    duration_ms: int


def _soldier_identity(engine: Engine, soldier_id: int) -> tuple[int, str]:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT persona_id, platform
                FROM soldiers
                WHERE soldier_id = :soldier_id
                """
            ),
            {"soldier_id": soldier_id},
        ).one_or_none()
    if row is None:
        raise RuntimeError(f"soldier {soldier_id} no longer exists")
    return int(row.persona_id), str(row.platform)


def collect_one_detailed_job(
    engine: Engine,
    *,
    identity: CollectorIdentity,
    request_interval_seconds: float,
    lease_seconds: int = 120,
    timeout_seconds: float = 15.0,
    retry_after_seconds: int = 300,
    allowed_soldier_ids: Sequence[int] | None = None,
    max_total_attempts: int | None = None,
) -> CollectedJob | FailedJob | None:
    """Claim and execute at most one detailed job.

    Optional cohort/attempt bounds are enforced atomically by the durable queue
    claim before any request-gate reservation or Battlelog request occurs.

    Source/HTTP failures are classified, recorded, and returned to pending with
    future eligibility. BF4PS/database/programming exceptions still propagate:
    pretending an infrastructure failure was safely persisted would be wrong.
    """
    if retry_after_seconds < 0:
        raise ValueError("retry_after_seconds must be non-negative")

    with engine.begin() as conn:
        job = claim_next_job(
            conn,
            collector_uuid=identity.collector_uuid,
            lane=identity.lane,
            resource="detailed",
            lease_seconds=lease_seconds,
            allowed_soldier_ids=allowed_soldier_ids,
            max_total_attempts=max_total_attempts,
        )
        if job is None:
            return None
        if not mark_job_running(conn, job):
            raise RuntimeError("claimed detailed job could not transition to running")

    persona_id, platform = _soldier_identity(engine, job.soldier_id)

    # Gate reservation must commit before waiting or issuing HTTP so other
    # processes sharing this egress identity see the same outbound budget.
    with engine.begin() as conn:
        permit = reserve_request_slot(
            conn,
            egress_key=identity.egress_key,
            interval_seconds=request_interval_seconds,
        )

    if permit.wait_seconds > 0:
        sleep(permit.wait_seconds)

    started = monotonic()
    try:
        fetched = fetch_detailed_stats(
            persona_id,
            platform,
            timeout_seconds=timeout_seconds,
        )
        stats = normalize_detailed_stats(
            fetched.payload,
            expected_persona_id=persona_id,
            expected_platform_int=fetched.platform_int,
        )
    except DetailedStatsError as exc:
        duration_ms = max(0, int((monotonic() - started) * 1000))
        attempted_at = datetime.now(timezone.utc)
        failure = classify_detailed_failure(exc)
        with engine.begin() as conn:
            persist_detailed_retry_failure(
                conn,
                job=job,
                failure=failure,
                attempted_at=attempted_at,
                persona_id=persona_id,
                platform=platform,
                collector_name=identity.collector_name,
                hostname=identity.hostname,
                egress_key=identity.egress_key,
                duration_ms=duration_ms,
                retry_after_seconds=retry_after_seconds,
            )
        return FailedJob(
            job_id=job.job_id,
            soldier_id=job.soldier_id,
            persona_id=persona_id,
            platform=platform,
            error_class=failure.error_class,
            http_status=failure.http_status,
            retry_after_seconds=retry_after_seconds,
            duration_ms=duration_ms,
        )

    duration_ms = max(0, int((monotonic() - started) * 1000))
    source_fetched_at = datetime.now(timezone.utc)

    with engine.begin() as conn:
        history_appended = persist_detailed_success(
            conn,
            job=job,
            stats=stats,
            source_fetched_at=source_fetched_at,
            persona_id=persona_id,
            platform=platform,
            collector_name=identity.collector_name,
            hostname=identity.hostname,
            egress_key=identity.egress_key,
            duration_ms=duration_ms,
            http_status=200,
        )

    return CollectedJob(
        job_id=job.job_id,
        soldier_id=job.soldier_id,
        persona_id=persona_id,
        platform=platform,
        history_appended=history_appended,
        duration_ms=duration_ms,
    )
