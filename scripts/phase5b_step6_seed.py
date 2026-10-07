#!/usr/bin/env python3
"""Seed the frozen Phase 5B Step 6 run marker and exactly 27 queue jobs."""
from __future__ import annotations

from sqlalchemy import text

from bf4ps.collection_jobs import enqueue_job
from bf4ps.db import make_engine
from bf4ps.phase5b_step6_cohort import (
    COHORT, EXPECTED_DATABASE, EXPECTED_REVISION, GLOBAL_ATTEMPT_CEILING,
    JOB_REASON, PRIORITY_VALUE, RESOURCES, RUN_MARKER_EVENT_TYPE, RUN_NUMBER,
    SOLDIER_IDS,
)


def _assert_target(conn) -> None:
    assert conn.execute(text("SELECT current_database()")).scalar_one() == EXPECTED_DATABASE
    assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == EXPECTED_REVISION
    assert conn.execute(text("SELECT pg_is_in_recovery()")).scalar_one() is False
    assert conn.execute(text("SELECT current_setting('transaction_read_only')")).scalar_one() == "off"


def main() -> int:
    engine = make_engine()
    with engine.begin() as conn:
        _assert_target(conn)
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('bf4ps:phase5b-step6-seed'))"))

        markers = int(conn.execute(text("""
            SELECT count(*) FROM collection_events
            WHERE event_type=:event_type
              AND metadata->>'run_number'=:run_number
        """), {"event_type": RUN_MARKER_EVENT_TYPE, "run_number": str(RUN_NUMBER)}).scalar_one())
        assert markers == 0, f"Step 6 run marker already exists: {markers}"

        existing = int(conn.execute(text("""
            SELECT count(*) FROM collection_jobs
            WHERE soldier_id=ANY(:ids)
        """), {"ids": list(SOLDIER_IDS)}).scalar_one())
        assert existing == 0, f"cohort queue is not clean: {existing} jobs"

        foreign_background = int(conn.execute(text("""
            SELECT count(*) FROM collection_jobs
            WHERE lane='background' AND NOT (soldier_id=ANY(:ids))
        """), {"ids": list(SOLDIER_IDS)}).scalar_one())
        assert foreign_background == 0, f"foreign background jobs exist: {foreign_background}"

        marker = conn.execute(text("""
            INSERT INTO collection_events (
                event_type, result, lane, metadata
            ) VALUES (
                :event_type, 'started', 'background',
                jsonb_build_object(
                    'run_number', CAST(:run_number AS integer),
                    'cohort_size', CAST(:cohort_size AS integer),
                    'resources', CAST(:resources AS jsonb),
                    'physical_attempt_ceiling', CAST(:ceiling AS integer)
                )
            )
            RETURNING event_id
        """), {
            "event_type": RUN_MARKER_EVENT_TYPE,
            "run_number": RUN_NUMBER,
            "cohort_size": len(COHORT),
            "resources": '["detailed","weapons","vehicles"]',
            "ceiling": GLOBAL_ATTEMPT_CEILING,
        }).scalar_one()

        job_ids = []
        for soldier_id, _persona, _name, _platform in COHORT:
            for resource in RESOURCES:
                job_ids.append(enqueue_job(
                    conn, soldier_id=soldier_id, resource=resource,
                    lane="background", priority_class="bootstrap",
                    reason=JOB_REASON, priority_value=PRIORITY_VALUE,
                ))

        rows = conn.execute(text("""
            SELECT soldier_id, resource, lane, priority_class, reason,
                   status, attempt_count, collector_uuid, lease_token
            FROM collection_jobs
            WHERE soldier_id=ANY(:ids)
        """), {"ids": list(SOLDIER_IDS)}).mappings().all()
        assert len(rows) == GLOBAL_ATTEMPT_CEILING
        assert all(r["resource"] in RESOURCES for r in rows)
        assert all(r["lane"] == "background" and r["priority_class"] == "bootstrap" for r in rows)
        assert all(r["reason"] == JOB_REASON and r["status"] == "pending" for r in rows)
        assert all(int(r["attempt_count"]) == 0 for r in rows)
        assert all(r["collector_uuid"] is None and r["lease_token"] is None for r in rows)

    print("===== BF4PS PHASE 5B STEP 6 SEED =====")
    print(f"run_marker_event_id={marker}")
    print(f"queue_jobs={len(job_ids)} expected={GLOBAL_ATTEMPT_CEILING}")
    print("queue_shape=background/bootstrap/pending/attempt0/unowned")
    print("Battlelog requests: 0")
    print("PHASE 5B STEP 6 SEED: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
