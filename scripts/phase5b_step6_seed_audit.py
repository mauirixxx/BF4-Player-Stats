#!/usr/bin/env python3
"""Read-only audit of the seeded Phase 5B Step 6 queue."""
from __future__ import annotations
from sqlalchemy import text
from bf4ps.db import make_engine
from bf4ps.phase5b_step6_cohort import (
    EXPECTED_DATABASE, EXPECTED_REVISION, GLOBAL_ATTEMPT_CEILING, JOB_REASON,
    RESOURCES, RUN_MARKER_EVENT_TYPE, RUN_NUMBER, SOLDIER_IDS,
)


def main() -> int:
    engine = make_engine()
    with engine.connect() as conn:
        assert conn.execute(text("SELECT current_database()")).scalar_one() == EXPECTED_DATABASE
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == EXPECTED_REVISION

        marker = conn.execute(text("""
            SELECT event_id, metadata FROM collection_events
            WHERE event_type=:event_type AND metadata->>'run_number'=:run_number
            ORDER BY event_id DESC
        """), {"event_type": RUN_MARKER_EVENT_TYPE, "run_number": str(RUN_NUMBER)}).mappings().all()
        assert len(marker) == 1
        boundary = int(marker[0]["event_id"])

        rows = conn.execute(text("""
            SELECT soldier_id, resource, lane, priority_class, reason,
                   status, attempt_count, collector_uuid, lease_token
            FROM collection_jobs
            WHERE soldier_id=ANY(:ids)
        """), {"ids": list(SOLDIER_IDS)}).mappings().all()
        assert len(rows) == GLOBAL_ATTEMPT_CEILING
        pairs = {(int(r["soldier_id"]), str(r["resource"])) for r in rows}
        assert len(pairs) == GLOBAL_ATTEMPT_CEILING
        assert {r for _s, r in pairs} == set(RESOURCES)
        assert all(r["lane"] == "background" and r["priority_class"] == "bootstrap" for r in rows)
        assert all(r["reason"] == JOB_REASON and r["status"] == "pending" for r in rows)
        assert all(int(r["attempt_count"]) == 0 for r in rows)
        assert all(r["collector_uuid"] is None and r["lease_token"] is None for r in rows)

        attempts = int(conn.execute(text("""
            SELECT count(*) FROM collection_events
            WHERE event_id>:boundary AND soldier_id=ANY(:ids)
              AND resource=ANY(:resources)
              AND event_type='collection_attempt_started'
        """), {"boundary": boundary, "ids": list(SOLDIER_IDS), "resources": list(RESOURCES)}).scalar_one())
        assert attempts == 0

    print("===== BF4PS PHASE 5B STEP 6 SEEDED-QUEUE AUDIT =====")
    print(f"run_marker_event_id={boundary}")
    print(f"queue_jobs={len(rows)} unique_soldier_resource_pairs={len(pairs)}")
    print("queue_shape=background/bootstrap/pending/attempt0/unowned")
    print("physical attempts after marker: 0")
    print("database writes: 0")
    print("Battlelog requests: 0")
    print("PHASE 5B STEP 6 SEEDED-QUEUE AUDIT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
