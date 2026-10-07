#!/usr/bin/env python3
"""Read-only preflight for Phase 5B Step 6 bounded live validation."""
from __future__ import annotations

from sqlalchemy import text

from bf4ps.db import make_engine
from bf4ps.phase5b_step6_cohort import (
    COHORT, EXPECTED_DATABASE, EXPECTED_REVISION, GLOBAL_ATTEMPT_CEILING,
    RESOURCES, RUN_MARKER_EVENT_TYPE, RUN_NUMBER, SOLDIER_IDS,
)


def main() -> int:
    engine = make_engine()
    with engine.connect() as conn:
        db = conn.execute(text("SELECT current_database()")).scalar_one()
        revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        recovery = bool(conn.execute(text("SELECT pg_is_in_recovery()")).scalar_one())
        read_only = conn.execute(text("SELECT current_setting('transaction_read_only')")).scalar_one()
        assert db == EXPECTED_DATABASE
        assert revision == EXPECTED_REVISION
        assert recovery is False
        assert read_only == "off"

        rows = conn.execute(text("""
            SELECT soldier_id, persona_id, current_name, platform
            FROM soldiers WHERE soldier_id = ANY(:ids)
            ORDER BY soldier_id
        """), {"ids": list(SOLDIER_IDS)}).mappings().all()
        actual = {
            int(r["soldier_id"]): (int(r["persona_id"]), str(r["current_name"]), str(r["platform"]))
            for r in rows
        }
        assert len(actual) == len(COHORT)
        for soldier_id, persona_id, name, platform in COHORT:
            assert actual[soldier_id] == (persona_id, name, platform)

        state_rows = conn.execute(text("""
            SELECT soldier_id FROM collection_state
            WHERE soldier_id = ANY(:ids)
        """), {"ids": list(SOLDIER_IDS)}).all()
        assert len(state_rows) == len(COHORT)

        cohort_jobs = conn.execute(text("""
            SELECT soldier_id, resource, lane, status, collector_uuid
            FROM collection_jobs
            WHERE soldier_id = ANY(:ids)
        """), {"ids": list(SOLDIER_IDS)}).mappings().all()
        assert not cohort_jobs, f"cohort already has queue work: {cohort_jobs}"

        foreign_owned = conn.execute(text("""
            SELECT count(*) FROM collection_jobs
            WHERE status IN ('claimed','running')
              AND soldier_id = ANY(:ids)
        """), {"ids": list(SOLDIER_IDS)}).scalar_one()
        assert int(foreign_owned) == 0

        markers = conn.execute(text("""
            SELECT count(*) FROM collection_events
            WHERE event_type=:event_type
              AND metadata->>'run_number'=:run_number
        """), {"event_type": RUN_MARKER_EVENT_TYPE, "run_number": str(RUN_NUMBER)}).scalar_one()
        assert int(markers) == 0, "Step 6 run marker already exists"

    print("===== BF4PS PHASE 5B STEP 6 READ-ONLY PREFLIGHT =====")
    print(f"database={EXPECTED_DATABASE} revision={EXPECTED_REVISION} primary_writable=yes")
    print(f"cohort={len(COHORT)} soldiers platforms=3pc/3ps4/3xboxone")
    print(f"resources={','.join(RESOURCES)} physical_attempt_ceiling={GLOBAL_ATTEMPT_CEILING}")
    print("cohort identities: exact match")
    print("collection_state rows: complete")
    print("cohort queue work: 0")
    print("existing Step 6 run markers: 0")
    print("database writes: 0")
    print("Battlelog requests: 0")
    print("PHASE 5B STEP 6 PREFLIGHT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
