"""Bounded Phase 2 materialization of detailed bootstrap work."""

from __future__ import annotations

from dataclasses import dataclass

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
) -> FeederResult:
    """Replenish a bounded background/detailed bootstrap working set.

    Phase 2 deliberately requires an explicit soldier boundary.  ``None`` is
    rejected rather than meaning "all soldiers" so a development invocation
    cannot accidentally materialize the complete BF4PS backlog.
    """
    if target_depth <= 0:
        raise ValueError("target_depth must be positive")
    if max_soldier_id is None:
        raise ValueError("max_soldier_id is required for the Phase 2 safety boundary")
    if max_soldier_id <= 0:
        raise ValueError("max_soldier_id must be positive")

    # Serialize feeder passes.  This lock is transaction-scoped, so crashes do
    # not leave a separate coordinator/lease to repair.
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('bf4ps:phase2:detailed-feeder'))"))

    actionable_before = int(
        conn.execute(
            text(
                """
                SELECT COUNT(*)
                FROM collection_jobs
                WHERE resource = 'detailed'
                  AND lane = 'background'
                  AND status IN ('pending', 'claimed', 'running')
                """
            )
        ).scalar_one()
    )
    deficit = max(0, target_depth - actionable_before)

    created = 0
    if deficit:
        # Never-attempted state is the Phase 2 eligibility boundary.  Existing
        # actionable work is excluded explicitly in addition to the queue's
        # unique constraint so repeated feeder passes are naturally idempotent.
        rows = conn.execute(
            text(
                """
                SELECT s.soldier_id
                FROM soldiers AS s
                JOIN collection_state AS cs
                  ON cs.soldier_id = s.soldier_id
                WHERE s.soldier_id <= :max_soldier_id
                  AND s.platform IN ('pc', 'ps4', 'xboxone')
                  AND cs.detailed_state = 'never_attempted'
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
            {"max_soldier_id": max_soldier_id, "deficit": deficit},
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

    actionable_after = int(
        conn.execute(
            text(
                """
                SELECT COUNT(*)
                FROM collection_jobs
                WHERE resource = 'detailed'
                  AND lane = 'background'
                  AND status IN ('pending', 'claimed', 'running')
                """
            )
        ).scalar_one()
    )

    if actionable_after > target_depth:
        raise RuntimeError(
            "bounded feeder invariant violated: actionable depth exceeds target"
        )

    return FeederResult(
        target_depth=target_depth,
        actionable_before=actionable_before,
        deficit=deficit,
        created=created,
        actionable_after=actionable_after,
    )
