"""Phase 1 single-job detailed collector orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from time import monotonic, sleep
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Engine

from bf4ps.battlelog_detailed import fetch_detailed_stats, normalize_detailed_stats
from bf4ps.collection_jobs import ClaimedJob, claim_next_job, mark_job_running
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
) -> CollectedJob | None:
    """Claim, fetch, normalize, and atomically persist at most one detailed job.

    Phase 1 deliberately performs no worker loop here.  The caller invokes this
    function once; no job means a clean ``None`` return.
    """
    with engine.begin() as conn:
        job = claim_next_job(
            conn,
            collector_uuid=identity.collector_uuid,
            lane=identity.lane,
            resource="detailed",
            lease_seconds=lease_seconds,
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
