"""Bounded Phase 2 materialization of detailed bootstrap work."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from sqlalchemy import text
from sqlalchemy.engine import Connection


@dataclass(frozen=True)
class FeederResult:
    target_depth: int
    actionable_before: int
    deficit: int
    created: int
    actionable_after: int


def replenish_detailed_bootstrap(
    conn: Connection,
    *,
    target_depth: int,
    max_soldier_id: int | None,
    allowed_soldier_ids: Sequence[int] | None = None,
    max_total_attempts: int | None = None,
) -> FeederResult:
    """Replenish a bounded background/detailed bootstrap working set.

    Phase 2 deliberately requires an explicit soldier boundary. ``None`` is
    rejected rather than meaning "all soldiers" so a development invocation
    cannot accidentally materialize the complete BF4PS backlog.

    ``allowed_soldier_ids`` optionally narrows that already-bounded population
    to an explicit validation cohort. It never expands the max-soldier safety
    boundary and is primarily useful for controlled cross-platform exercises.

    ``max_total_attempts`` is an additional experiment boundary. Completed
    attempts come from the event ledger and currently claimed/running jobs are
    treated as reserved attempts. The feeder will not create more immediately
    actionable jobs than can still be claimed before that ceiling.

    Working depth means work that can consume a collector *now*: claimed and
    running jobs plus pending jobs whose ``eligible_at`` has arrived. Pending
    retry jobs in cooldown remain preserved in the queue but do not block the
    feeder from materializing another never-attempted soldier. When an explicit
    cohort is supplied, depth accounting is scoped to that same cohort.

    ``target_depth`` is a replenishment target, not a globally exclusive queue
    invariant. Feeder passes are serialized, but collectors may concurrently
    change job state around a feeder transaction. Consequently the final depth
    is returned as telemetry and may transiently exceed the target; the feeder
    itself only materializes the deficit observed while holding its advisory
    transaction lock.
    """
    if target_depth <= 0:
        raise ValueError("target_depth must be positive")
    if max_soldier_id is None:
        raise ValueError("max_soldier_id is required for the Phase 2 safety boundary")
    if max_soldier_id <= 0:
        raise ValueError("max_soldier_id must be positive")
    if max_total_attempts is not None and max_total_attempts <= 0:
        raise ValueError("max_total_attempts must be positive")

    allowed_ids: tuple[int, ...] | None = None
    if allowed_soldier_ids is not None:
        allowed_ids = tuple(dict.fromkeys(int(value) for value in allowed_soldier_ids))
        if not allowed_ids:
            raise ValueError("allowed_soldier_ids must not be empty when provided")
        if any(value <= 0 for value in allowed_ids):
            raise ValueError("allowed_soldier_ids must contain only positive IDs")
        if any(value > max_soldier_id for value in allowed_ids):
            raise ValueError("allowed_soldier_ids cannot exceed max_soldier_id")
    if max_total_attempts is not None and allowed_ids is None:
        raise ValueError("max_total_attempts requires allowed_soldier_ids")

    # Serialize feeder passes. This lock is transaction-scoped, so crashes do
    # not leave a separate coordinator/lease to repair.
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('bf4ps:phase2:detailed-feeder'))"))

    depth_cohort_clause = ""
    depth_params: dict[str, object] = {"max_soldier_id": max_soldier_id}
    if allowed_ids is not None:
        depth_cohort_clause = "AND soldier_id = ANY(:allowed_soldier_ids)"
        depth_params["allowed_soldier_ids"] = list(allowed_ids)

    depth_sql = text(
        f"""
        SELECT COUNT(*)
        FROM collection_jobs
        WHERE resource = 'detailed'
          AND lane = 'background'
          AND soldier_id <= :max_soldier_id
          {depth_cohort_clause}
          AND (
                status IN ('claimed', 'running')
                OR (status = 'pending' AND eligible_at <= now())
          )
        """
    )

    actionable_before = int(conn.execute(depth_sql, depth_params).scalar_one())
    deficit = max(0, target_depth - actionable_before)

    if max_total_attempts is not None:
        event_clause = "AND soldier_id = ANY(:allowed_soldier_ids)"
        completed_attempts = int(
            conn.execute(
                text(
                    f"""
                    SELECT COUNT(*)
                    FROM collection_events
                    WHERE resource = 'detailed'
                      AND lane = 'background'
                      {event_clause}
                      AND event_type IN ('collection_success', 'collection_failure')
                    """
                ),
                depth_params,
            ).scalar_one()
        )
        active_attempts = int(
            conn.execute(
                text(
                    f"""
                    SELECT COUNT(*)
                    FROM collection_jobs
                    WHERE resource = 'detailed'
                      AND lane = 'background'
                      AND soldier_id <= :max_soldier_id
                      {depth_cohort_clause}
                      AND status IN ('claimed', 'running')
                    """
                ),
                depth_params,
            ).scalar_one()
        )
        pending_actionable = max(0, actionable_before - active_attempts)
        remaining_claims = max(0, max_total_attempts - completed_attempts - active_attempts)
        materialization_budget = max(0, remaining_claims - pending_actionable)
        deficit = min(deficit, materialization_budget)

    created = 0
    if deficit:
        cohort_clause = ""
        params: dict[str, object] = {
            "max_soldier_id": max_soldier_id,
            "deficit": deficit,
        }
        if allowed_ids is not None:
            cohort_clause = "AND s.soldier_id = ANY(:allowed_soldier_ids)"
            params["allowed_soldier_ids"] = list(allowed_ids)

        # Never-attempted state is the Phase 2 eligibility boundary. Existing
        # queue work is excluded explicitly in addition to the queue's unique
        # constraint so repeated feeder passes are naturally idempotent.
        rows = conn.execute(
            text(
                f"""
                SELECT s.soldier_id
                FROM soldiers AS s
                JOIN collection_state AS cs
                  ON cs.soldier_id = s.soldier_id
                WHERE s.soldier_id <= :max_soldier_id
                  AND s.platform IN ('pc', 'ps4', 'xboxone')
                  AND cs.detailed_state = 'never_attempted'
                  {cohort_clause}
                  AND NOT EXISTS (
                        SELECT 1
                        FROM collection_jobs AS j
                        WHERE j.soldier_id = s.soldier_id
                          AND j.resource = 'detailed'
                  )
                ORDER BY s.soldier_id ASC
                LIMIT :deficit
                """
            ),
            params,
        ).scalars().all()

        for soldier_id in rows:
            result = conn.execute(
                text(
                    """
                    INSERT INTO collection_jobs
                        (soldier_id, resource, lane, priority_class, reason,
                         status, priority_value, eligible_at)
                    VALUES
                        (:soldier_id, 'detailed', 'background', 'bootstrap',
                         'bootstrap', 'pending', 0, now())
                    ON CONFLICT (soldier_id, resource) DO NOTHING
                    """
                ),
                {"soldier_id": int(soldier_id)},
            )
            created += int(result.rowcount or 0)

    # This is intentionally observational. A collector can change queue state
    # concurrently with the serialized feeder pass, so target_depth cannot be
    # enforced as a global instantaneous postcondition here.
    actionable_after = int(conn.execute(depth_sql, depth_params).scalar_one())

    return FeederResult(
        target_depth=target_depth,
        actionable_before=actionable_before,
        deficit=deficit,
        created=created,
        actionable_after=actionable_after,
    )
