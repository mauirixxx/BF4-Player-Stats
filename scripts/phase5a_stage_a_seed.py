#!/usr/bin/env python3
"""Seed exactly the frozen 30 Phase 5A Stage A weapon jobs."""
from __future__ import annotations

from sqlalchemy import text

from bf4ps.collection_jobs import enqueue_job
from bf4ps.db import make_engine
from bf4ps.phase5a_frozen_cohort import FROZEN_COHORT
from phase5a_stage_a_common import (
    GLOBAL_ATTEMPT_CEILING, JOB_REASON, PRIORITY_VALUE, SOLDIER_IDS, assert_target,
    terminal_attempts,
)

def main() -> int:
    print("===== BF4PS PHASE 5A STAGE A WEAPON SEED =====")
    engine = make_engine()
    with engine.begin() as conn:
        assert_target(conn)
        assert terminal_attempts(conn) == 0, "cohort already has weapon attempt events"
        foreign = int(conn.execute(text("""
            SELECT count(*) FROM collection_jobs
            WHERE lane='background'
              AND NOT (resource='weapons' AND soldier_id=ANY(:ids))
        """), {"ids": list(SOLDIER_IDS)}).scalar_one())
        assert foreign == 0, f"foreign background jobs exist: {foreign}"

        existing = int(conn.execute(text("""
            SELECT count(*) FROM collection_jobs
            WHERE resource='weapons' AND soldier_id=ANY(:ids)
        """), {"ids": list(SOLDIER_IDS)}).scalar_one())
        assert existing == 0, f"cohort weapon jobs already exist: {existing}"

        job_ids = []
        for soldier_id, _persona_id, _name, _platform in FROZEN_COHORT:
            job_ids.append(enqueue_job(
                conn,
                soldier_id=int(soldier_id),
                resource="weapons",
                lane="background",
                priority_class="bootstrap",
                reason=JOB_REASON,
                priority_value=PRIORITY_VALUE,
            ))

        rows = conn.execute(text("""
            SELECT job_id, soldier_id, resource, lane, reason, status, attempt_count
            FROM collection_jobs
            WHERE resource='weapons' AND soldier_id=ANY(:ids)
            ORDER BY soldier_id
        """), {"ids": list(SOLDIER_IDS)}).mappings().all()
        assert len(rows) == GLOBAL_ATTEMPT_CEILING
        assert all(r["status"] == "pending" and int(r["attempt_count"]) == 0 for r in rows)
        assert all(r["reason"] == JOB_REASON for r in rows)

    print(f"seeded weapon jobs: {job_ids}")
    print("database writes: 30 queue rows")
    print("Battlelog requests: 0")
    print("PHASE 5A STAGE A WEAPON SEED: PASS")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
