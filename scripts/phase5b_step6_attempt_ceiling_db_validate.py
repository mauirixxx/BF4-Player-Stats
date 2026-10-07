#!/usr/bin/env python3
"""Rollback-only validation of the Step 6 aggregate multi-resource attempt ceiling.

No Battlelog requests are made. This harness uses existing cohort soldiers,
creates transaction-local collector/jobs/events, proves mixed-resource durable
attempts plus a reserved claim share one global ceiling, then rolls back.
"""
from __future__ import annotations

import argparse
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


def run_validation(synthetic_ids: list[int]) -> None:
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

        if len(synthetic_ids) != 3 or len(set(synthetic_ids)) != 3:
            raise RuntimeError("provide exactly three distinct validation soldier IDs")
        if set(synthetic_ids) & set(SOLDIER_IDS):
            raise RuntimeError("validation soldiers must not be in the live Step 6 cohort")
        found = conn.execute(
            text("SELECT soldier_id FROM soldiers WHERE soldier_id = ANY(:ids) FOR UPDATE"),
            {"ids": synthetic_ids},
        ).scalars().all()
        if set(found) != set(synthetic_ids):
            raise RuntimeError("one or more validation soldiers do not exist")
        owned = conn.execute(
            text(
                """
                SELECT soldier_id, resource, status
                FROM collection_jobs
                WHERE soldier_id = ANY(:ids)
                  AND status IN ('claimed', 'running')
                """
            ),
            {"ids": synthetic_ids},
        ).mappings().all()
        if owned:
            raise RuntimeError(f"validation soldiers have owned jobs: {owned}")
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
        job_ids: dict[str, int] = {}
        for soldier_id, resource in zip(synthetic_ids, RESOURCES, strict=True):
            job_id = conn.execute(
                text(
                    """
                    INSERT INTO collection_jobs
                        (soldier_id, resource, lane, priority_class, reason,
                         status, priority_value, eligible_at)
                    VALUES
                        (:soldier_id, :resource, 'background', 'bootstrap',
                         'phase5b_step6_ceiling_validate', 'pending', 0, now())
                    RETURNING job_id
                    """
                ),
                {"soldier_id": soldier_id, "resource": resource},
            ).scalar_one()
            job_ids[resource] = int(job_id)

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
                        (job_id, soldier_id, resource, lane, event_type, attempt_number)
                    VALUES
                        (:job_id, :soldier_id, :resource, 'background',
                         'collection_attempt_started', 1)
                    """
                ),
                {
                    "job_id": job_ids[resource],
                    "soldier_id": soldier_id,
                    "resource": resource,
                },
            )

        durable_count = int(
            conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM (
                        SELECT job_id, attempt_number
                        FROM collection_events
                        WHERE event_id > :boundary
                          AND soldier_id = ANY(:ids)
                          AND resource = ANY(:resources)
                          AND lane = 'background'
                          AND event_type = 'collection_attempt_started'
                        GROUP BY job_id, attempt_number
                    ) AS attempts
                    """
                ),
                {
                    "boundary": boundary,
                    "ids": synthetic_ids,
                    "resources": list(RESOURCES),
                },
            ).scalar_one()
        )
        assert durable_count == 2

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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--soldier-id", type=int, action="append", required=True)
    args = parser.parse_args()
    ids = list(dict.fromkeys(args.soldier_id))
    if len(ids) != 3 or any(value <= 0 for value in ids):
        parser.error("provide exactly three distinct positive --soldier-id values")
    run_validation(ids)


if __name__ == "__main__":
    main()
