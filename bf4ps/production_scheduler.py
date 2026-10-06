"""Phase 5B observation-driven production job materialization.

This module implements the frozen scheduling eligibility policy only. It does
not run collectors, bypass the durable queue, or scan the historical backlog.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.engine import Connection

RETAINED_RESOURCES = ("detailed", "weapons", "vehicles")


@dataclass(frozen=True)
class MaterializeResult:
    soldier_id: int
    source_class: str
    created_resources: tuple[str, ...]


def materialize_bf4sw_observation(
    conn: Connection,
    *,
    soldier_id: int,
    observed_at: datetime,
    as_of: datetime,
    newly_discovered: bool,
) -> MaterializeResult:
    """Materialize independently eligible work for one BF4SW observation.

    New soldiers are eligible for one bootstrap attempt of each retained-stat
    resource. Returning soldiers only generate active work when the source
    observation is within the active window and that resource's persisted
    next-due timestamp has arrived. Recent/inactive observations do not create
    new refresh debt.

    Existing jobs are never rewritten. The queue's unique (soldier, resource)
    key provides idempotence across overlapping discovery/reconciliation input.
    """
    if soldier_id <= 0:
        raise ValueError("soldier_id must be positive")
    if observed_at.tzinfo is None or as_of.tzinfo is None:
        raise ValueError("observed_at and as_of must be timezone-aware")
    if observed_at > as_of:
        raise ValueError("observed_at cannot be later than as_of")

    row = conn.execute(
        text(
            """
            SELECT ss.first_seen_at, ss.last_seen_at,
                   cs.detailed_state, cs.detailed_next_due_at,
                   cs.weapons_state, cs.weapons_next_due_at,
                   cs.vehicles_state, cs.vehicles_next_due_at
            FROM soldier_sources AS ss
            JOIN collection_state AS cs ON cs.soldier_id = ss.soldier_id
            WHERE ss.soldier_id = :soldier_id
              AND ss.source_type = 'bf4sw'
            """
        ),
        {"soldier_id": soldier_id},
    ).mappings().one()

    # Classify the latest retained source observation against an explicit
    # scheduler clock. This prevents delayed reconciliation of old source rows
    # from being mistaken for current activity.
    source_age_seconds = max(0.0, (as_of - row["last_seen_at"]).total_seconds())
    if source_age_seconds <= 24 * 60 * 60:
        source_class = "active"
    elif source_age_seconds <= 7 * 24 * 60 * 60:
        source_class = "recent"
    else:
        source_class = "inactive"

    eligible: list[tuple[str, str, str]] = []
    for resource in RETAINED_RESOURCES:
        state = row[f"{resource}_state"]
        next_due = row[f"{resource}_next_due_at"]

        if newly_discovered and state == "never_attempted":
            eligible.append((resource, "bootstrap", "bf4sw_new_soldier"))
            continue

        if (
            not newly_discovered
            and source_class == "active"
            and state == "success"
            and next_due is not None
            and next_due <= observed_at
        ):
            eligible.append((resource, "active", "bf4sw_active_refresh"))

    created: list[str] = []
    for resource, priority_class, reason in eligible:
        result = conn.execute(
            text(
                """
                INSERT INTO collection_jobs
                    (soldier_id, resource, lane, priority_class, reason,
                     status, priority_value, eligible_at)
                VALUES
                    (:soldier_id, :resource, 'background', :priority_class,
                     :reason, 'pending', 0, :observed_at)
                ON CONFLICT (soldier_id, resource) DO NOTHING
                """
            ),
            {
                "soldier_id": soldier_id,
                "resource": resource,
                "priority_class": priority_class,
                "reason": reason,
                "observed_at": observed_at,
            },
        )
        if int(result.rowcount or 0):
            created.append(resource)

    return MaterializeResult(
        soldier_id=soldier_id,
        source_class=source_class,
        created_resources=tuple(created),
    )
