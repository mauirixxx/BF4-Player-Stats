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
from bf4ps.background_service import claim_production_background_job
from bf4ps.detailed_failure import classify_detailed_failure, persist_detailed_retry_failure
from bf4ps.detailed_persistence import persist_detailed_success
from bf4ps.request_gate import reserve_request_slot
from bf4ps.retry_policy import retry_delay_for_failure


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



def _record_detailed_attempt_started(
    engine: Engine,
    *,
    job,
    identity: CollectorIdentity,
    persona_id: int,
    platform: str,
) -> None:
    """Durably record the physical outbound attempt before issuing HTTP."""
    with engine.begin() as conn:
        owned = conn.execute(
            text(
                """
                SELECT 1
                FROM collection_jobs
                WHERE job_id = :job_id
                  AND soldier_id = :soldier_id
                  AND resource = 'detailed'
                  AND status = 'running'
                  AND collector_uuid = :collector_uuid
                  AND lease_token = :lease_token
                  AND lease_expires_at > now()
                FOR UPDATE
                """
            ),
            {
                "job_id": job.job_id,
                "soldier_id": job.soldier_id,
                "collector_uuid": job.collector_uuid,
                "lease_token": job.lease_token,
            },
        ).one_or_none()
        if owned is None:
            raise RuntimeError("detailed attempt start rejected: job lease is no longer owned")

        duplicate = conn.execute(
            text(
                """
                SELECT 1 FROM collection_events
                WHERE job_id = :job_id
                  AND attempt_number = :attempt_number
                  AND event_type = 'collection_attempt_started'
                  AND metadata->>'physical_request' = 'true'
                LIMIT 1
                """
            ),
            {"job_id": job.job_id, "attempt_number": job.attempt_count},
        ).one_or_none()
        if duplicate is not None:
            raise RuntimeError("detailed attempt start rejected: physical start already recorded")

        conn.execute(
            text(
                """
                INSERT INTO collection_events
                    (collector_uuid, collector_name_snapshot, hostname_snapshot,
                     egress_key_snapshot, job_id, soldier_id, persona_id, platform,
                     resource, lane, event_type, attempt_number, lease_token,
                     metadata)
                VALUES
                    (:collector_uuid, :collector_name, :hostname, :egress_key,
                     :job_id, :soldier_id, :persona_id, :platform,
                     'detailed', :lane, 'collection_attempt_started',
                     :attempt_number, :lease_token,
                     jsonb_build_object(
                         'physical_request', true,
                         'priority_class', (
                             SELECT priority_class FROM collection_jobs
                             WHERE job_id = :job_id
                         ),
                         'retry', (
                             SELECT last_error_at IS NOT NULL FROM collection_jobs
                             WHERE job_id = :job_id
                         )
                     ))
                """
            ),
            {
                "collector_uuid": job.collector_uuid,
                "collector_name": identity.collector_name,
                "hostname": identity.hostname,
                "egress_key": identity.egress_key,
                "job_id": job.job_id,
                "soldier_id": job.soldier_id,
                "persona_id": persona_id,
                "platform": platform,
                "lane": job.lane,
                "attempt_number": job.attempt_count,
                "lease_token": job.lease_token,
            },
        )



def _record_detailed_persistence_failure(
    engine: Engine,
    *,
    job,
    identity: CollectorIdentity,
    persona_id: int,
    platform: str,
    duration_ms: int,
    exc: Exception,
) -> None:
    """Best-effort diagnostic after successful-fetch persistence rolls back."""
    error_class = f"{exc.__class__.__module__}.{exc.__class__.__name__}"
    error_message = (str(exc).strip() or exc.__class__.__name__)[:2000]
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO collection_events
                        (collector_uuid, collector_name_snapshot, hostname_snapshot,
                         egress_key_snapshot, job_id, soldier_id, persona_id, platform,
                         resource, lane, event_type, attempt_number, result, duration_ms,
                         error_class, error_message, lease_token, metadata)
                    VALUES
                        (:collector_uuid, :collector_name, :hostname, :egress_key,
                         :job_id, :soldier_id, :persona_id, :platform,
                         'detailed', :lane, 'collection_persistence_failure',
                         :attempt_number, 'persistence_failure', :duration_ms,
                         :error_class, :error_message, :lease_token,
                         jsonb_build_object('stage', 'persist_detailed_success'))
                    """
                ),
                {
                    "collector_uuid": job.collector_uuid,
                    "collector_name": identity.collector_name,
                    "hostname": identity.hostname,
                    "egress_key": identity.egress_key,
                    "job_id": job.job_id,
                    "soldier_id": job.soldier_id,
                    "persona_id": persona_id,
                    "platform": platform,
                    "lane": job.lane,
                    "attempt_number": job.attempt_count,
                    "duration_ms": duration_ms,
                    "error_class": error_class,
                    "error_message": error_message,
                    "lease_token": job.lease_token,
                },
            )
    except Exception as logging_exc:
        print(
            "WARNING: failed to persist collection_persistence_failure "
            f"job={job.job_id} original={error_class} "
            f"logging_error={logging_exc.__class__.__name__}: {logging_exc}",
            flush=True,
        )


def collect_one_detailed_job(
    engine: Engine,
    *,
    identity: CollectorIdentity,
    request_interval_seconds: float,
    lease_seconds: int = 120,
    timeout_seconds: float = 15.0,
    retry_after_seconds: int | None = None,
    allowed_soldier_ids: Sequence[int] | None = None,
    max_total_attempts: int | None = None,
    attempts_after_event_id: int | None = None,
    attempt_ceiling_resources: Sequence[str] | None = None,
    enforce_production_budget: bool = False,
) -> CollectedJob | FailedJob | None:
    """Claim and execute at most one detailed job.

    Optional cohort/attempt bounds are enforced atomically by the durable queue
    claim before any request-gate reservation or Battlelog request occurs.

    Source/HTTP failures are classified, recorded, and returned to pending with
    future eligibility. BF4PS/database/programming exceptions still propagate:
    pretending an infrastructure failure was safely persisted would be wrong.
    """
    if retry_after_seconds is not None and retry_after_seconds < 0:
        raise ValueError("retry_after_seconds must be non-negative")

    with engine.begin() as conn:
        if enforce_production_budget and identity.lane == "background":
            job = claim_production_background_job(
                conn,
                collector_uuid=identity.collector_uuid,
                resource="detailed",
                lease_seconds=lease_seconds,
                allowed_soldier_ids=allowed_soldier_ids,
                max_total_attempts=max_total_attempts,
                attempts_after_event_id=attempts_after_event_id,
                attempt_ceiling_resources=attempt_ceiling_resources,
            )
        else:
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

    _record_detailed_attempt_started(
        engine,
        job=job,
        identity=identity,
        persona_id=persona_id,
        platform=platform,
    )

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
        with engine.connect() as conn:
            effective_retry_after_seconds = (
                retry_after_seconds
                if retry_after_seconds is not None
                else retry_delay_for_failure(
                    conn,
                    soldier_id=job.soldier_id,
                    resource="detailed",
                )
            )
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
                retry_after_seconds=effective_retry_after_seconds,
            )
        return FailedJob(
            job_id=job.job_id,
            soldier_id=job.soldier_id,
            persona_id=persona_id,
            platform=platform,
            error_class=failure.error_class,
            http_status=failure.http_status,
            retry_after_seconds=effective_retry_after_seconds,
            duration_ms=duration_ms,
        )

    duration_ms = max(0, int((monotonic() - started) * 1000))
    source_fetched_at = datetime.now(timezone.utc)

    try:
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
    except RuntimeError as exc:
        if "detailed success rejected: job lease is no longer owned" in str(exc):
            # Persistence has rolled back. Only a committed competing success
            # qualifies as a duplicate; otherwise preserve the original error.
            with engine.begin() as conn:
                from bf4ps.distributed_duplicate_events import record_discarded_duplicate
                if record_discarded_duplicate(
                    conn, job=job, persona_id=persona_id, platform=platform,
                    collector_name=identity.collector_name,
                    hostname=identity.hostname, egress_key=identity.egress_key,
                    duration_ms=duration_ms, http_status=200,
                ):
                    return None
        raise
    except Exception as exc:
        _record_detailed_persistence_failure(
            engine,
            job=job,
            identity=identity,
            persona_id=persona_id,
            platform=platform,
            duration_ms=duration_ms,
            exc=exc,
        )
        raise

    return CollectedJob(
        job_id=job.job_id,
        soldier_id=job.soldier_id,
        persona_id=persona_id,
        platform=platform,
        history_appended=history_appended,
        duration_ms=duration_ms,
    )
