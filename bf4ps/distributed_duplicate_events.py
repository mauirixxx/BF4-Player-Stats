"""Classify stale collection results without mistaking failures for duplicates.

Uses the documented collection_events schema. Caller owns the transaction.
A stale lease alone is NOT proof that another collector committed a winner.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import Connection

from bf4ps.collection_jobs import ClaimedJob


@dataclass(frozen=True)
class StaleResultClassification:
    duplicate: bool
    reason: str
    winner_event_id: int | None


def classify_stale_result(conn: Connection, *, job: ClaimedJob) -> StaleResultClassification:
    """Only an actual success event for the same job proves a competing winner."""
    row = conn.execute(
        text("""
            SELECT event_id
            FROM collection_events
            WHERE job_id = :job_id
              AND soldier_id = :soldier_id
              AND resource = :resource
              AND event_type = 'collection_success'
            ORDER BY event_id ASC
            LIMIT 1
        """),
        {"job_id": job.job_id, "soldier_id": job.soldier_id, "resource": job.resource},
    ).one_or_none()
    if row is None:
        return StaleResultClassification(False, "stale_lease_without_confirmed_winner", None)
    return StaleResultClassification(True, "confirmed_competing_success", int(row[0]))


def record_discarded_duplicate(
    conn: Connection,
    *,
    job: ClaimedJob,
    persona_id: int,
    platform: str,
    collector_name: str,
    hostname: str,
    egress_key: str,
    duration_ms: int,
    http_status: int,
) -> bool:
    """Record a confirmed redundant completed fetch; never store its payload.

    Returns False if no committed winner is visible. Job ID is deliberately
    metadata-only because successful collection deletes collection_jobs.
    """
    if job.resource not in {"detailed", "weapons", "vehicles"}:
        raise ValueError("unsupported retained resource")
    if platform not in {"pc", "ps4", "xboxone"}:
        raise ValueError("unsupported platform")
    if persona_id <= 0 or duration_ms < 0 or not 100 <= http_status <= 599:
        raise ValueError("invalid duplicate observation")
    # Serialize duplicate evidence for this exact job/attempt across processes.
    # The advisory lock is transaction-scoped and must be held through commit.
    conn.execute(
        text("""
            SELECT pg_advisory_xact_lock(
                hashtext('bf4ps:duplicate-discard'),
                hashtext(:attempt_identity)
            )
        """),
        {"attempt_identity": f"{job.job_id}:{job.attempt_count}:{job.lease_token}"},
    )
    already_recorded = conn.execute(
        text("""
            SELECT 1 FROM collection_events
            WHERE event_type = 'collection_duplicate_discarded'
              AND metadata->>'original_job_id' = :original_job_id
              AND metadata->>'original_lease_token' = :original_lease_token
              AND attempt_number = :attempt_number
            LIMIT 1
        """),
        {"original_job_id": str(job.job_id),
         "original_lease_token": str(job.lease_token),
         "attempt_number": job.attempt_count},
    ).one_or_none()
    if already_recorded is not None:
        return False
    verdict = classify_stale_result(conn, job=job)
    if not verdict.duplicate:
        return False
    conn.execute(
        text("""
            INSERT INTO collection_events
                (collector_name_snapshot, hostname_snapshot, egress_key_snapshot,
                 soldier_id, persona_id, platform, resource, lane, event_type,
                 attempt_number, result, duration_ms, http_status, metadata)
            VALUES
                (:collector_name, :hostname, :egress_key, :soldier_id,
                 :persona_id, :platform, :resource, :lane,
                 'collection_duplicate_discarded', :attempt_number,
                 'duplicate_discarded', :duration_ms, :http_status,
                 jsonb_build_object(
                     'original_job_id', :job_id,
                     'original_collector_uuid', :collector_uuid,
                     'original_lease_token', :lease_token,
                     'winner_event_id', :winner_event_id,
                     'reason', 'confirmed_competing_success'))
        """),
        {
            "collector_name": collector_name, "hostname": hostname,
            "egress_key": egress_key, "soldier_id": job.soldier_id,
            "persona_id": persona_id, "platform": platform,
            "resource": job.resource, "lane": job.lane,
            "attempt_number": job.attempt_count, "duration_ms": duration_ms,
            "http_status": http_status, "job_id": job.job_id,
            "collector_uuid": str(job.collector_uuid),
            "lease_token": str(job.lease_token),
            "winner_event_id": verdict.winner_event_id,
        },
    )
    return True
