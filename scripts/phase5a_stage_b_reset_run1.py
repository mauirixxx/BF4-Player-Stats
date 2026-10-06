#!/usr/bin/env python3
"""Guarded reset of the Stage B vehicle probe into distributed Run #1."""
from __future__ import annotations

from sqlalchemy import text

from bf4ps.db import make_engine
from phase5a_stage_b_common import (
    FROZEN_UUIDS, GLOBAL_ATTEMPT_CEILING, PROBE_BOUNDARY_EVENT_ID,
    PROBE_EVENT_TYPE, PROBE_JOB_ID, PROBE_SOLDIER_ID, RUN_MARKER_EVENT_TYPE,
    RUN_NUMBER, SOLDIER_IDS, assert_target,
)


def main() -> int:
    print("===== BF4PS PHASE 5A STAGE B RUN #1 GUARDED RESET =====")
    print("preserves: Stage A weapon state/data/history + Stage B probe events/catalog")
    print("Battlelog requests: 0")
    engine = make_engine()
    with engine.begin() as conn:
        assert_target(conn)

        existing = int(conn.execute(text("""
            SELECT count(*) FROM collection_events
            WHERE event_type=:event_type AND metadata->>'run_number'=:run_number
        """), {"event_type": RUN_MARKER_EVENT_TYPE, "run_number": str(RUN_NUMBER)}).scalar_one())
        assert existing == 0, f"Stage B Run #{RUN_NUMBER} marker already exists"

        probe = conn.execute(text("""
            SELECT event_id FROM collection_events
            WHERE event_id=:event_id AND event_type=:event_type
              AND soldier_id=:soldier_id
        """), {
            "event_id": PROBE_BOUNDARY_EVENT_ID, "event_type": PROBE_EVENT_TYPE,
            "soldier_id": PROBE_SOLDIER_ID,
        }).one_or_none()
        assert probe is not None, "expected exact preserved Stage B probe boundary"

        starts = int(conn.execute(text("""
            SELECT count(*) FROM collection_events
            WHERE resource='vehicles' AND soldier_id=:soldier_id
              AND event_type='collection_attempt_started'
              AND event_id>:boundary
        """), {"soldier_id": PROBE_SOLDIER_ID, "boundary": PROBE_BOUNDARY_EVENT_ID}).scalar_one())
        successes = int(conn.execute(text("""
            SELECT count(*) FROM collection_events
            WHERE resource='vehicles' AND soldier_id=:soldier_id
              AND event_type='collection_success' AND result='success'
              AND http_status=200 AND job_id=:job_id AND event_id>:boundary
        """), {
            "soldier_id": PROBE_SOLDIER_ID, "job_id": PROBE_JOB_ID,
            "boundary": PROBE_BOUNDARY_EVENT_ID,
        }).scalar_one())
        persistence_failures = int(conn.execute(text("""
            SELECT count(*) FROM collection_events
            WHERE resource='vehicles' AND soldier_id=:soldier_id
              AND event_type='collection_persistence_failure'
              AND event_id>:boundary
        """), {"soldier_id": PROBE_SOLDIER_ID, "boundary": PROBE_BOUNDARY_EVENT_ID}).scalar_one())
        assert starts == 1 and successes == 1 and persistence_failures == 0, (
            f"probe evidence mismatch starts={starts} successes={successes} "
            f"persistence_failures={persistence_failures}"
        )

        jobs = int(conn.execute(text("""
            SELECT count(*) FROM collection_jobs
            WHERE resource IN ('weapons','vehicles') OR lane='background'
        """)).scalar_one())
        assert jobs == 0, f"expected empty weapon/vehicle/background queue, found {jobs}"

        owners = int(conn.execute(text("""
            SELECT count(*) FROM collectors
            WHERE collector_uuid=ANY(:uuids) AND current_job_id IS NOT NULL
        """), {"uuids": list(FROZEN_UUIDS)}).scalar_one())
        assert owners == 0, f"frozen collectors are not idle: {owners}"

        states = conn.execute(text("""
            SELECT soldier_id, weapons_state, vehicles_state
            FROM collection_state
            WHERE soldier_id=ANY(:ids)
            ORDER BY soldier_id FOR UPDATE
        """), {"ids": list(SOLDIER_IDS)}).mappings().all()
        assert len(states) == GLOBAL_ATTEMPT_CEILING
        assert all(r["weapons_state"] == "success" for r in states), "Stage A weapon state changed"
        assert sum(r["vehicles_state"] == "success" for r in states) == 1, "expected exactly one vehicle success"
        assert next(r for r in states if r["soldier_id"] == PROBE_SOLDIER_ID)["vehicles_state"] == "success"
        assert all(
            r["vehicles_state"] == "never_attempted"
            for r in states if r["soldier_id"] != PROBE_SOLDIER_ID
        ), "non-probe vehicle state is not pristine"

        weapon_soldiers = int(conn.execute(text("""
            SELECT count(DISTINCT soldier_id) FROM soldier_weapon_stats
            WHERE soldier_id=ANY(:ids)
        """), {"ids": list(SOLDIER_IDS)}).scalar_one())
        assert weapon_soldiers == GLOBAL_ATTEMPT_CEILING, (
            f"Stage A weapon persistence missing for {GLOBAL_ATTEMPT_CEILING-weapon_soldiers} soldier(s)"
        )

        vehicle_shape = conn.execute(text("""
            SELECT count(*) AS rows, count(DISTINCT soldier_id) AS soldiers
            FROM soldier_vehicle_stats WHERE soldier_id=ANY(:ids)
        """), {"ids": list(SOLDIER_IDS)}).mappings().one()
        assert int(vehicle_shape["rows"]) == 82 and int(vehicle_shape["soldiers"]) == 1, (
            f"expected only 82 probe vehicle rows, found {dict(vehicle_shape)}"
        )

        deleted = conn.execute(text("""
            DELETE FROM soldier_vehicle_stats WHERE soldier_id=:soldier_id
        """), {"soldier_id": PROBE_SOLDIER_ID})
        assert deleted.rowcount == 82, f"expected 82 probe rows deleted, got {deleted.rowcount}"

        reset = conn.execute(text("""
            UPDATE collection_state
            SET vehicles_state='never_attempted',
                vehicles_last_attempt_at=NULL,
                vehicles_last_success_at=NULL,
                vehicles_next_due_at=NULL,
                vehicles_consecutive_failures=0,
                vehicles_last_error_class=NULL,
                vehicles_last_error_message=NULL,
                updated_at=now()
            WHERE soldier_id=:soldier_id
        """), {"soldier_id": PROBE_SOLDIER_ID})
        assert reset.rowcount == 1

        marker = conn.execute(text("""
            INSERT INTO collection_events (event_type, result, metadata)
            VALUES (:event_type, 'started',
                    jsonb_build_object(
                        'phase','5A','stage','B','resource','vehicles',
                        'run_number',:run_number,
                        'max_physical_attempts',:ceiling,
                        'preserved_probe_boundary',:probe_boundary))
            RETURNING event_id
        """), {
            "event_type": RUN_MARKER_EVENT_TYPE, "run_number": RUN_NUMBER,
            "ceiling": GLOBAL_ATTEMPT_CEILING,
            "probe_boundary": PROBE_BOUNDARY_EVENT_ID,
        }).scalar_one()

        post_rows = int(conn.execute(text("""
            SELECT count(*) FROM soldier_vehicle_stats WHERE soldier_id=ANY(:ids)
        """), {"ids": list(SOLDIER_IDS)}).scalar_one())
        pristine = int(conn.execute(text("""
            SELECT count(*) FROM collection_state
            WHERE soldier_id=ANY(:ids)
              AND vehicles_state='never_attempted'
              AND vehicles_last_attempt_at IS NULL
              AND vehicles_last_success_at IS NULL
              AND vehicles_next_due_at IS NULL
              AND vehicles_consecutive_failures=0
              AND vehicles_last_error_class IS NULL
              AND vehicles_last_error_message IS NULL
        """), {"ids": list(SOLDIER_IDS)}).scalar_one())
        assert post_rows == 0 and pristine == GLOBAL_ATTEMPT_CEILING

    print(f"preserved probe boundary event_id: {PROBE_BOUNDARY_EVENT_ID}")
    print(f"deleted current probe vehicle rows: {deleted.rowcount}")
    print("reset vehicle collection states: 1")
    print(f"Stage B Run #{RUN_NUMBER} boundary event_id: {marker}")
    print("Stage A weapon state/data preserved for all 30 soldiers")
    print("Battlelog requests: 0")
    print("PHASE 5A STAGE B RUN #1 GUARDED RESET: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
