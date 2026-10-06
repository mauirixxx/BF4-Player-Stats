#!/usr/bin/env python3
"""Guarded reset from preserved Stage A Run #1 evidence to pristine Run #2 state."""
from __future__ import annotations

from sqlalchemy import text

from bf4ps.db import make_engine
from phase5a_stage_a_common import (
    FROZEN_UUIDS, GLOBAL_ATTEMPT_CEILING, RUN_MARKER_EVENT_TYPE, RUN_NUMBER,
    SOLDIER_IDS, assert_target,
)


def main() -> int:
    print("===== BF4PS PHASE 5A STAGE A RUN #2 GUARDED RESET =====")
    print("preserves: all Run #1 collection_events")
    print("Battlelog requests: 0")
    engine = make_engine()
    with engine.begin() as conn:
        assert_target(conn)

        existing_marker = int(conn.execute(text("""
            SELECT count(*) FROM collection_events
            WHERE event_type=:event_type
              AND metadata->>'run_number'=:run_number
        """), {"event_type": RUN_MARKER_EVENT_TYPE, "run_number": str(RUN_NUMBER)}).scalar_one())
        assert existing_marker == 0, f"Run #{RUN_NUMBER} marker already exists"

        terminal = int(conn.execute(text("""
            SELECT count(*) FROM collection_events
            WHERE resource='weapons' AND lane='background'
              AND soldier_id=ANY(:ids)
              AND event_type IN ('collection_success','collection_failure')
        """), {"ids": list(SOLDIER_IDS)}).scalar_one())
        assert terminal == GLOBAL_ATTEMPT_CEILING, f"expected 30 preserved Run #1 terminal events, found {terminal}"

        physical = int(conn.execute(text("""
            SELECT count(*) FROM collection_events
            WHERE resource='weapons' AND lane='background'
              AND soldier_id=ANY(:ids)
              AND event_type='collection_attempt_started'
        """), {"ids": list(SOLDIER_IDS)}).scalar_one())
        assert physical == 0, f"expected legacy Run #1 to have zero durable physical markers, found {physical}"

        jobs = int(conn.execute(text("""
            SELECT count(*) FROM collection_jobs
            WHERE resource IN ('weapons','vehicles') OR lane='background'
        """)).scalar_one())
        assert jobs == 0, f"expected no weapon/vehicle/background jobs before reset, found {jobs}"

        owners = int(conn.execute(text("""
            SELECT count(*) FROM collectors
            WHERE collector_uuid=ANY(:uuids) AND current_job_id IS NOT NULL
        """), {"uuids": list(FROZEN_UUIDS)}).scalar_one())
        assert owners == 0, f"frozen collectors are not idle: {owners}"

        states = conn.execute(text("""
            SELECT soldier_id, weapons_state, vehicles_state
            FROM collection_state
            WHERE soldier_id=ANY(:ids)
            ORDER BY soldier_id
            FOR UPDATE
        """), {"ids": list(SOLDIER_IDS)}).mappings().all()
        assert len(states) == GLOBAL_ATTEMPT_CEILING, f"expected 30 collection_state rows, found {len(states)}"
        assert all(r["weapons_state"] == "success" for r in states), "Run #1 weapon states are not uniformly success"
        assert all(r["vehicles_state"] == "never_attempted" for r in states), "vehicle state is not pristine"

        weapon_soldiers = int(conn.execute(text("""
            SELECT count(DISTINCT soldier_id)
            FROM soldier_weapon_stats
            WHERE soldier_id=ANY(:ids)
        """), {"ids": list(SOLDIER_IDS)}).scalar_one())
        assert weapon_soldiers == GLOBAL_ATTEMPT_CEILING, f"expected weapon rows for all 30 soldiers, found {weapon_soldiers}"

        vehicle_rows = int(conn.execute(text("""
            SELECT count(*) FROM soldier_vehicle_stats WHERE soldier_id=ANY(:ids)
        """), {"ids": list(SOLDIER_IDS)}).scalar_one())
        assert vehicle_rows == 0, f"vehicle rows are not pristine: {vehicle_rows}"

        deleted = conn.execute(text("""
            DELETE FROM soldier_weapon_stats WHERE soldier_id=ANY(:ids)
        """), {"ids": list(SOLDIER_IDS)})
        assert deleted.rowcount > 0, "expected Run #1 weapon rows to delete"

        reset = conn.execute(text("""
            UPDATE collection_state
            SET weapons_state='never_attempted',
                weapons_last_attempt_at=NULL,
                weapons_last_success_at=NULL,
                weapons_next_due_at=NULL,
                weapons_consecutive_failures=0,
                weapons_last_error_class=NULL,
                weapons_last_error_message=NULL,
                updated_at=now()
            WHERE soldier_id=ANY(:ids)
        """), {"ids": list(SOLDIER_IDS)})
        assert reset.rowcount == GLOBAL_ATTEMPT_CEILING, f"expected 30 state resets, got {reset.rowcount}"

        marker = conn.execute(text("""
            INSERT INTO collection_events
                (event_type, result, metadata)
            VALUES
                (:event_type, 'started',
                 jsonb_build_object(
                     'phase', '5A',
                     'stage', 'A',
                     'resource', 'weapons',
                     'run_number', :run_number,
                     'purpose', 'distributed_deadlock_and_accounting_fix_validation'
                 ))
            RETURNING event_id
        """), {"event_type": RUN_MARKER_EVENT_TYPE, "run_number": RUN_NUMBER}).scalar_one()

        post_rows = int(conn.execute(text("""
            SELECT count(*) FROM soldier_weapon_stats WHERE soldier_id=ANY(:ids)
        """), {"ids": list(SOLDIER_IDS)}).scalar_one())
        post_states = int(conn.execute(text("""
            SELECT count(*) FROM collection_state
            WHERE soldier_id=ANY(:ids)
              AND weapons_state='never_attempted'
              AND weapons_last_attempt_at IS NULL
              AND weapons_last_success_at IS NULL
              AND weapons_next_due_at IS NULL
              AND weapons_consecutive_failures=0
              AND weapons_last_error_class IS NULL
              AND weapons_last_error_message IS NULL
        """), {"ids": list(SOLDIER_IDS)}).scalar_one())
        assert post_rows == 0
        assert post_states == GLOBAL_ATTEMPT_CEILING

    print(f"preserved Run #1 terminal events: {terminal}")
    print(f"deleted Run #1 per-soldier weapon rows: {deleted.rowcount}")
    print(f"reset weapon collection states: {reset.rowcount}")
    print(f"Run #{RUN_NUMBER} boundary event_id: {marker}")
    print("Battlelog requests: 0")
    print("PHASE 5A STAGE A RUN #2 GUARDED RESET: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
