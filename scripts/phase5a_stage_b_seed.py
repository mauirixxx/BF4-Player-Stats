#!/usr/bin/env python3
"""Seed exactly the frozen 30 Phase 5A Stage B vehicle jobs."""
from __future__ import annotations
from sqlalchemy import text
from bf4ps.collection_jobs import enqueue_job
from bf4ps.db import make_engine
from bf4ps.phase5a_frozen_cohort import FROZEN_COHORT
from phase5a_stage_b_common import (
    GLOBAL_ATTEMPT_CEILING, JOB_REASON, PRIORITY_VALUE, SOLDIER_IDS,
    assert_target, current_run_start_event_id,
)
def main()->int:
    print("===== BF4PS PHASE 5A STAGE B VEHICLE SEED =====")
    engine=make_engine()
    with engine.begin() as conn:
        assert_target(conn); boundary=current_run_start_event_id(conn)
        attempts=int(conn.execute(text("""
            SELECT count(*) FROM collection_events
            WHERE resource='vehicles' AND soldier_id=ANY(:ids) AND event_id>:boundary
              AND event_type='collection_attempt_started'
        """),{"ids":list(SOLDIER_IDS),"boundary":boundary}).scalar_one())
        assert attempts==0, f"current Stage B run already has {attempts} physical attempts"
        foreign=int(conn.execute(text("""
            SELECT count(*) FROM collection_jobs
            WHERE lane='background'
              AND NOT (resource='vehicles' AND soldier_id=ANY(:ids))
        """),{"ids":list(SOLDIER_IDS)}).scalar_one())
        assert foreign==0, f"foreign background jobs exist: {foreign}"
        existing=int(conn.execute(text("""
            SELECT count(*) FROM collection_jobs
            WHERE resource='vehicles' AND soldier_id=ANY(:ids)
        """),{"ids":list(SOLDIER_IDS)}).scalar_one())
        assert existing==0, f"cohort vehicle jobs already exist: {existing}"
        ids=[]
        for soldier_id,_persona,_name,_platform in FROZEN_COHORT:
            ids.append(enqueue_job(conn,soldier_id=int(soldier_id),resource="vehicles",
                lane="background",priority_class="bootstrap",reason=JOB_REASON,
                priority_value=PRIORITY_VALUE))
        rows=conn.execute(text("""
            SELECT job_id,status,attempt_count,reason FROM collection_jobs
            WHERE resource='vehicles' AND soldier_id=ANY(:ids)
        """),{"ids":list(SOLDIER_IDS)}).mappings().all()
        assert len(rows)==GLOBAL_ATTEMPT_CEILING
        assert all(r["status"]=="pending" and int(r["attempt_count"])==0 and r["reason"]==JOB_REASON for r in rows)
    print(f"seeded vehicle jobs: {ids}")
    print("database writes: 30 queue rows")
    print("Battlelog requests: 0")
    print("PHASE 5A STAGE B VEHICLE SEED: PASS")
    return 0
if __name__=="__main__": raise SystemExit(main())
