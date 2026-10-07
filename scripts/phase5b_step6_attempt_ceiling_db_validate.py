#!/usr/bin/env python3
"""Rollback-only validation of the Step 6 aggregate multi-resource attempt ceiling.

No Battlelog requests are made. This harness uses existing cohort soldiers,
creates transaction-local collector/jobs/events, proves mixed-resource durable
attempts plus a reserved claim share one global ceiling, then rolls back.
"""
from __future__ import annotations

from uuid import uuid4

from sqlalchemy import text

from bf4ps.collection_jobs import claim_next_job
from bf4ps.db import make_engine
from bf4ps.phase5b_step6_cohort import (
    EXPECTED_DATABASE,
    EXPECTED_REVISION,
    RESOURCES,
    SOLDIER_IDS,
)


def run_validation() -> None:
    engine = make_engine()
    conn = engine.connect()
    tx = conn.begin()
    try:
        assert conn.execute(text("SELECT current_database()")).scalar_one() == EXPECTED_DATABASE
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == EXPECTED_REVISION

        existing = conn.execute(
            text("SELECT COUNT(*) FROM collection_jobs WHERE soldier_id = ANY(:ids)"),
            {"ids": list(SOLDIER_IDS)},
        ).scalar_one()
        if int(existing) != 27:
            raise RuntimeError(f"expected live seeded Step 6 queue to remain at 27 jobs; found {existing}")

        # Synthetic identities avoid touching the real Step 6 queue while still
        # exercising the exact PostgreSQL ceiling query.
        synthetic_ids = list(SOLDIER_IDS[:3])
        conn.execute(
            text("DELETE FROM collection_jobs WHERE soldier_id = ANY(:ids)"),
            {"ids": synthetic_ids},
        )
        collector_uuid = uuid4()
        conn.execute(
            text(
                """
                INSERT INTO collectors
                    (collector_uuid, collector_name, hostname, lane, egress_key,
                     enabled, drained, heartbeat_state)
                VALUES
                    (:uuid, :name, 'phase5b-step6-ceiling-validate', 'background',
                     :egress, true, false, 'healthy')
                """
            ),
            {
                "uuid": collector_uuid,
                "name": f"phase5b-step6-ceiling-validate-{collector_uuid}",
                "egress": f"phase5b-step6-ceiling-validate-{collector_uuid}",
            },
        )
        for soldier_id, resource in zip(synthetic_ids, RESOURCES, strict=True):
            conn.execute(
                text(
                    """
                    INSERT INTO collection_jobs
                        (soldier_id, resource, lane, priority_class, reason,
                         status, priority_value, eligible_at)
                    VALUES
                        (:soldier_id, :resource, 'background', 'bootstrap',
                         'phase5b_step6_ceiling_validate', 'pending', 0, now())
                    """
                ),
                {"soldier_id": soldier_id, "resource": resource},
            )

        boundary = int(
            conn.execute(
                text("SELECT COALESCE(MAX(event_id), 0) FROM collection_events")
            ).scalar_one()
        )

        # Two durable starts on different resources consume two global slots.
        for soldier_id, resource in zip(synthetic_ids[:2], RESOURCES[:2], strict=True):
            conn.execute(
                text(
                    """
                    INSERT INTO collection_events
                        (soldier_id, resource, lane, event_type, attempt_number)
                    VALUES
                        (:soldier_id, :resource, 'background',
                         'collection_attempt_started', 1)
                    """
                ),
                {"soldier_id": soldier_id, "resource": resource},
            )

        # Ceiling=3: with two durable starts, exactly one mixed-resource claim
        # may be reserved. A fourth aggregate reservation must be refused.
        claimed = claim_next_job(
            conn,
            collector_uuid=collector_uuid,
            resource="vehicles",
            allowed_soldier_ids=synthetic_ids,
            max_total_attempts=3,
            attempts_after_event_id=boundary,
            attempt_ceiling_resources=RESOURCES,
        )
        assert claimed is not None
        blocked = claim_next_job(
            conn,
            collector_uuid=collector_uuid,
            resource="detailed",
            allowed_soldier_ids=synthetic_ids,
            max_total_attempts=3,
            attempts_after_event_id=boundary,
            attempt_ceiling_resources=RESOURCES,
        )
        assert blocked is None

        print("PASS: Phase 5B Step 6 aggregate attempt-ceiling DB validation")
        print("  resources: detailed + weapons + vehicles")
        print("  durable mixed-resource starts: 2")
        print("  reserved mixed-resource claim: 1")
        print("  aggregate ceiling: 3")
        print("  next claim blocked: PASS")
        print("  Battlelog requests: 0")
        print("  committed database writes: 0 (transaction rolled back)")
    finally:
        if tx.is_active:
            tx.rollback()
        conn.close()
        engine.dispose()


if __name__ == "__main__":
    run_validation()
