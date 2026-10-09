"""PostgreSQL-coordinated Phase 5B background service admission."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from bf4ps.collection_jobs import ClaimedJob, claim_next_job

BACKGROUND_SLOTS_PER_HOUR = 1296
ACTIVE_SHARE = 0.75
BOOTSTRAP_FLOOR = 0.20
RECOVERY_FLOOR = 0.05

ACTIVE_SLOTS = int(BACKGROUND_SLOTS_PER_HOUR * ACTIVE_SHARE)
BOOTSTRAP_SLOTS = int(BACKGROUND_SLOTS_PER_HOUR * BOOTSTRAP_FLOOR)
RECOVERY_SLOTS = BACKGROUND_SLOTS_PER_HOUR - ACTIVE_SLOTS - BOOTSTRAP_SLOTS


@dataclass(frozen=True)
class BackgroundServiceUsage:
    total: int
    active: int
    bootstrap: int
    recovery: int


def _usage(conn: Connection) -> BackgroundServiceUsage:
    row = conn.execute(
        text(
            """
            WITH started AS (
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (
                        WHERE metadata->>'priority_class' = 'active'
                          AND COALESCE((metadata->>'retry')::boolean, false) = false
                    ) AS active,
                    COUNT(*) FILTER (
                        WHERE metadata->>'priority_class' = 'bootstrap'
                          AND COALESCE((metadata->>'retry')::boolean, false) = false
                    ) AS bootstrap,
                    COUNT(*) FILTER (
                        WHERE COALESCE((metadata->>'retry')::boolean, false) = true
                           OR metadata->>'priority_class' = 'recent'
                    ) AS recovery
                FROM collection_events
                WHERE lane = 'background'
                  AND event_type = 'collection_attempt_started'
                  AND occurred_at >= now() - interval '1 hour'
            ),
            reserved AS (
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (
                        WHERE priority_class = 'active' AND last_error_at IS NULL
                    ) AS active,
                    COUNT(*) FILTER (
                        WHERE priority_class = 'bootstrap' AND last_error_at IS NULL
                    ) AS bootstrap,
                    COUNT(*) FILTER (
                        WHERE last_error_at IS NOT NULL OR priority_class = 'recent'
                    ) AS recovery
                FROM collection_jobs AS j
                WHERE j.lane = 'background'
                  AND j.status IN ('claimed', 'running')
                  AND j.lease_expires_at > now()
                  AND NOT EXISTS (
                      SELECT 1
                      FROM collection_events AS e
                      WHERE e.job_id = j.job_id
                        AND e.attempt_number = j.attempt_count
                        AND e.event_type = 'collection_attempt_started'
                  )
            )
            SELECT
                started.total + reserved.total AS total,
                started.active + reserved.active AS active,
                started.bootstrap + reserved.bootstrap AS bootstrap,
                started.recovery + reserved.recovery AS recovery
            FROM started, reserved
            """
        )
    ).mappings().one()
    return BackgroundServiceUsage(
        total=int(row["total"]),
        active=int(row["active"]),
        bootstrap=int(row["bootstrap"]),
        recovery=int(row["recovery"]),
    )


def claim_production_background_job(
    conn: Connection,
    *,
    collector_uuid: UUID,
    resource: str,
    lease_seconds: int = 120,
    allowed_soldier_ids: Sequence[int] | None = None,
    max_total_attempts: int | None = None,
    attempts_after_event_id: int | None = None,
    attempt_ceiling_resources: Sequence[str] | None = None,
) -> ClaimedJob | None:
    """Claim one job under the frozen aggregate budget and fairness policy.

    The existing collection queue remains authoritative. This function only
    chooses which eligible queue class may consume the next background slot.
    A transaction advisory lock serializes distributed admission decisions.
    """
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('bf4ps:phase5b-background-service'))"))

    interactive_pending = conn.execute(
        text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM collection_jobs
                WHERE lane = 'interactive'
                  AND eligible_at <= now()
                  AND (
                      status = 'pending'
                      OR (status IN ('claimed', 'running') AND lease_expires_at <= now())
                  )
            )
            """
        )
    ).scalar_one()
    if interactive_pending:
        return None

    usage = _usage(conn)
    if usage.total >= BACKGROUND_SLOTS_PER_HOUR:
        return None

    # Starvation floors take precedence while their reserved share remains
    # unused. If no eligible job exists in a floor, the slot is immediately
    # borrowable by another class.
    if usage.bootstrap < BOOTSTRAP_SLOTS:
        job = claim_next_job(
            conn,
            collector_uuid=collector_uuid,
            lane="background",
            resource=resource,
            lease_seconds=lease_seconds,
            priority_classes=("bootstrap",),
            retry_only=False,
            allowed_soldier_ids=allowed_soldier_ids,
            max_total_attempts=max_total_attempts,
            attempts_after_event_id=attempts_after_event_id,
            attempt_ceiling_resources=attempt_ceiling_resources,
        )
        if job is not None:
            return job

    if usage.recovery < RECOVERY_SLOTS:
        job = claim_next_job(
            conn,
            collector_uuid=collector_uuid,
            lane="background",
            resource=resource,
            lease_seconds=lease_seconds,
            priority_classes=("active", "recent", "bootstrap"),
            retry_only=True,
            allowed_soldier_ids=allowed_soldier_ids,
            max_total_attempts=max_total_attempts,
            attempts_after_event_id=attempts_after_event_id,
            attempt_ceiling_resources=attempt_ceiling_resources,
        )
        if job is not None:
            return job
        job = claim_next_job(
            conn,
            collector_uuid=collector_uuid,
            lane="background",
            resource=resource,
            lease_seconds=lease_seconds,
            priority_classes=("recent",),
            retry_only=False,
            allowed_soldier_ids=allowed_soldier_ids,
            max_total_attempts=max_total_attempts,
            attempts_after_event_id=attempts_after_event_id,
            attempt_ceiling_resources=attempt_ceiling_resources,
        )
        if job is not None:
            return job

    if usage.active < ACTIVE_SLOTS:
        job = claim_next_job(
            conn,
            collector_uuid=collector_uuid,
            lane="background",
            resource=resource,
            lease_seconds=lease_seconds,
            priority_classes=("active",),
            retry_only=False,
            allowed_soldier_ids=allowed_soldier_ids,
            max_total_attempts=max_total_attempts,
            attempts_after_event_id=attempts_after_event_id,
            attempt_ceiling_resources=attempt_ceiling_resources,
        )
        if job is not None:
            return job

    # Borrow unused reservations. Existing queue ordering remains authoritative
    # within this final eligible background pool.
    return claim_next_job(
        conn,
        collector_uuid=collector_uuid,
        lane="background",
        resource=resource,
        lease_seconds=lease_seconds,
        allowed_soldier_ids=allowed_soldier_ids,
        max_total_attempts=max_total_attempts,
        attempts_after_event_id=attempts_after_event_id,
        attempt_ceiling_resources=attempt_ceiling_resources,
    )
