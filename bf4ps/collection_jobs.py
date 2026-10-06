"""Durable collection-job queue primitives for BF4PS collectors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Connection

SUPPORTED_RESOURCES = frozenset({"detailed", "profile", "weapons", "vehicles"})
SUPPORTED_LANES = frozenset({"background", "interactive"})
SUPPORTED_PRIORITY_CLASSES = frozenset({"interactive", "active", "recent", "bootstrap"})


@dataclass(frozen=True)
class ClaimedJob:
    job_id: int
    soldier_id: int
    resource: str
    lane: str
    attempt_count: int
    collector_uuid: UUID
    lease_token: UUID


def enqueue_job(
    conn: Connection,
    *,
    soldier_id: int,
    resource: str,
    lane: str = "background",
    priority_class: str = "bootstrap",
    reason: str = "manual",
    priority_value: int = 0,
) -> int:
    """Create actionable work, or return the existing job for this soldier/resource."""
    if resource not in SUPPORTED_RESOURCES:
        raise ValueError(f"unsupported resource: {resource}")
    if lane not in SUPPORTED_LANES:
        raise ValueError(f"unsupported lane: {lane}")
    if priority_class not in SUPPORTED_PRIORITY_CLASSES:
        raise ValueError(f"unsupported priority class: {priority_class}")
    if not reason.strip():
        raise ValueError("reason must not be empty")

    row = conn.execute(
        text(
            """
            INSERT INTO collection_jobs
                (soldier_id, resource, lane, priority_class, reason,
                 status, priority_value, eligible_at)
            VALUES
                (:soldier_id, :resource, :lane, :priority_class, :reason,
                 'pending', :priority_value, now())
            ON CONFLICT (soldier_id, resource) DO UPDATE
            SET priority_value = GREATEST(collection_jobs.priority_value, EXCLUDED.priority_value)
            RETURNING job_id
            """
        ),
        {
            "soldier_id": soldier_id,
            "resource": resource,
            "lane": lane,
            "priority_class": priority_class,
            "reason": reason,
            "priority_value": priority_value,
        },
    ).one()
    return int(row.job_id)


def claim_next_job(
    conn: Connection,
    *,
    collector_uuid: UUID,
    lane: str = "background",
    resource: str = "detailed",
    lease_seconds: int = 120,
    allowed_soldier_ids: Sequence[int] | None = None,
    max_total_attempts: int | None = None,
) -> ClaimedJob | None:
    """Atomically claim one pending/expired job with optional experiment bounds.

    ``allowed_soldier_ids`` narrows claims to an explicit cohort. When
    ``max_total_attempts`` is supplied, claims are serialized with a
    transaction-scoped advisory lock. Durable attempt-start/terminal events
    count unique (job_id, attempt_number) attempts, while currently owned
    claimed/running jobs without such an event count as reserved attempts.
    This keeps the ceiling durable even if post-request persistence rolls back.
    """
    if resource not in SUPPORTED_RESOURCES:
        raise ValueError(f"unsupported resource: {resource}")
    if lane not in SUPPORTED_LANES:
        raise ValueError(f"unsupported lane: {lane}")
    if lease_seconds <= 0:
        raise ValueError("lease_seconds must be positive")
    if max_total_attempts is not None and max_total_attempts <= 0:
        raise ValueError("max_total_attempts must be positive")

    allowed_ids: tuple[int, ...] | None = None
    if allowed_soldier_ids is not None:
        allowed_ids = tuple(dict.fromkeys(int(value) for value in allowed_soldier_ids))
        if not allowed_ids:
            raise ValueError("allowed_soldier_ids must not be empty when provided")
        if any(value <= 0 for value in allowed_ids):
            raise ValueError("allowed_soldier_ids must contain only positive IDs")
    if max_total_attempts is not None and allowed_ids is None:
        raise ValueError("max_total_attempts requires allowed_soldier_ids")

    params: dict[str, object] = {
        "resource": resource,
        "lane": lane,
        "collector_uuid": collector_uuid,
        "lease_seconds": lease_seconds,
    }
    cohort_clause = ""
    if allowed_ids is not None:
        cohort_clause = "AND soldier_id = ANY(:allowed_soldier_ids)"
        params["allowed_soldier_ids"] = list(allowed_ids)

    if max_total_attempts is not None:
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('bf4ps:bounded-claim'))"))
        used_attempts = int(
            conn.execute(
                text(
                    f"""
                    WITH durable_attempts AS (
                        SELECT job_id, attempt_number
                        FROM collection_events
                        WHERE resource = :resource
                          AND lane = :lane
                          {cohort_clause}
                          AND event_type IN (
                              'collection_attempt_started',
                              'collection_success',
                              'collection_failure'
                          )
                        GROUP BY job_id, attempt_number
                    )
                    SELECT
                        (SELECT COUNT(*) FROM durable_attempts)
                      + (SELECT COUNT(*)
                         FROM collection_jobs AS j
                         WHERE j.resource = :resource
                           AND j.lane = :lane
                           {cohort_clause}
                           AND j.status IN ('claimed', 'running')
                           AND NOT EXISTS (
                               SELECT 1
                               FROM durable_attempts AS d
                               WHERE d.job_id = j.job_id
                                 AND d.attempt_number = j.attempt_count
                           ))
                    """
                ),
                params,
            ).scalar_one()
        )
        if used_attempts >= max_total_attempts:
            return None

    lease_token = uuid4()
    params["lease_token"] = lease_token
    row = conn.execute(
        text(
            f"""
            WITH candidate AS (
                SELECT job_id
                FROM collection_jobs
                WHERE resource = :resource
                  AND lane = :lane
                  {cohort_clause}
                  AND eligible_at <= now()
                  AND (
                        status = 'pending'
                        OR (status IN ('claimed', 'running') AND lease_expires_at <= now())
                  )
                ORDER BY
                    CASE priority_class
                        WHEN 'interactive' THEN 4
                        WHEN 'active' THEN 3
                        WHEN 'recent' THEN 2
                        WHEN 'bootstrap' THEN 1
                        ELSE 0
                    END DESC,
                    priority_value DESC,
                    eligible_at ASC,
                    created_at ASC,
                    job_id ASC
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            UPDATE collection_jobs AS j
            SET status = 'claimed',
                collector_uuid = :collector_uuid,
                claimed_at = now(),
                started_at = NULL,
                lease_expires_at = now() + (:lease_seconds * interval '1 second'),
                lease_token = :lease_token,
                attempt_count = j.attempt_count + 1,
                updated_at = now()
            FROM candidate
            WHERE j.job_id = candidate.job_id
            RETURNING j.job_id, j.soldier_id, j.resource, j.lane,
                      j.attempt_count, j.collector_uuid, j.lease_token
            """
        ),
        params,
    ).one_or_none()
    if row is None:
        return None
    return ClaimedJob(
        job_id=int(row.job_id),
        soldier_id=int(row.soldier_id),
        resource=str(row.resource),
        lane=str(row.lane),
        attempt_count=int(row.attempt_count),
        collector_uuid=row.collector_uuid,
        lease_token=row.lease_token,
    )


def mark_job_running(conn: Connection, job: ClaimedJob) -> bool:
    """Move the currently owned unexpired lease from claimed to running."""
    result = conn.execute(
        text(
            """
            UPDATE collection_jobs
            SET status = 'running', started_at = now(), updated_at = now()
            WHERE job_id = :job_id
              AND collector_uuid = :collector_uuid
              AND lease_token = :lease_token
              AND status = 'claimed'
              AND lease_expires_at > now()
            """
        ),
        {"job_id": job.job_id, "collector_uuid": job.collector_uuid, "lease_token": job.lease_token},
    )
    return result.rowcount == 1


def renew_lease(conn: Connection, job: ClaimedJob, *, lease_seconds: int = 120) -> bool:
    """Extend an unexpired lease only for its current fencing token."""
    if lease_seconds <= 0:
        raise ValueError("lease_seconds must be positive")
    result = conn.execute(
        text(
            """
            UPDATE collection_jobs
            SET lease_expires_at = now() + (:lease_seconds * interval '1 second'), updated_at = now()
            WHERE job_id = :job_id
              AND collector_uuid = :collector_uuid
              AND lease_token = :lease_token
              AND status IN ('claimed', 'running')
              AND lease_expires_at > now()
            """
        ),
        {
            "job_id": job.job_id,
            "collector_uuid": job.collector_uuid,
            "lease_token": job.lease_token,
            "lease_seconds": lease_seconds,
        },
    )
    return result.rowcount == 1


def release_for_retry(conn: Connection, job: ClaimedJob, *, retry_after_seconds: int) -> bool:
    """Return currently owned work to pending without accepting a stale token."""
    if retry_after_seconds < 0:
        raise ValueError("retry_after_seconds must be non-negative")
    result = conn.execute(
        text(
            """
            UPDATE collection_jobs
            SET status = 'pending',
                eligible_at = now() + (:retry_after_seconds * interval '1 second'),
                collector_uuid = NULL,
                lease_token = NULL,
                claimed_at = NULL,
                started_at = NULL,
                lease_expires_at = NULL,
                updated_at = now()
            WHERE job_id = :job_id
              AND collector_uuid = :collector_uuid
              AND lease_token = :lease_token
              AND status IN ('claimed', 'running')
            """
        ),
        {
            "job_id": job.job_id,
            "collector_uuid": job.collector_uuid,
            "lease_token": job.lease_token,
            "retry_after_seconds": retry_after_seconds,
        },
    )
    return result.rowcount == 1


def finalize_owned_job(conn: Connection, job: ClaimedJob) -> bool:
    """Delete finalized work only while the caller still owns an unexpired running lease."""
    result = conn.execute(
        text(
            """
            DELETE FROM collection_jobs
            WHERE job_id = :job_id
              AND collector_uuid = :collector_uuid
              AND lease_token = :lease_token
              AND status = 'running'
              AND lease_expires_at > now()
            """
        ),
        {"job_id": job.job_id, "collector_uuid": job.collector_uuid, "lease_token": job.lease_token},
    )
    return result.rowcount == 1
