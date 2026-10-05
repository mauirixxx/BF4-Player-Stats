#!/usr/bin/env python3
"""Seed exactly one frozen Lifecycle B job using the production queue primitive."""
from sqlalchemy import create_engine, text
from bf4ps.collection_jobs import enqueue_job
from phase3e_lifecycle_b_common import *
from phase3e_lifecycle_b_cohort import SOLDIER_ID,PERSONA_ID,PLATFORM,CURRENT_NAME

def main()->int:
    e=create_engine(database_url(),pool_pre_ping=True)
    with e.begin() as c:
        assert_target(c)
        row=c.execute(text("""
            SELECT s.persona_id,s.platform,s.current_name,
                   cs.detailed_state,cs.detailed_last_attempt_at,cs.detailed_last_success_at,
                   cs.detailed_next_due_at,cs.detailed_consecutive_failures,
                   cs.detailed_last_error_class,cs.detailed_last_error_message
            FROM soldiers s JOIN collection_state cs USING (soldier_id)
            WHERE s.soldier_id=:sid FOR UPDATE OF cs
        """),{'sid':SOLDIER_ID}).mappings().one_or_none()
        if row is None or (int(row['persona_id']),row['platform'],row['current_name'])!=(PERSONA_ID,PLATFORM,CURRENT_NAME):
            raise RuntimeError("frozen Lifecycle B soldier identity drift")
        pristine=(row['detailed_state']=='never_attempted' and row['detailed_last_attempt_at'] is None and row['detailed_last_success_at'] is None and row['detailed_next_due_at'] is None and int(row['detailed_consecutive_failures'])==0 and row['detailed_last_error_class'] is None and row['detailed_last_error_message'] is None)
        if not pristine: raise RuntimeError("frozen Lifecycle B soldier is no longer pristine")
        existing=c.execute(text("SELECT job_id FROM collection_jobs WHERE soldier_id=:sid AND resource=:r"),{'sid':SOLDIER_ID,'r':RESOURCE}).scalar_one_or_none()
        if existing is not None: raise RuntimeError(f"frozen Lifecycle B job already exists: {existing}")
        job_id=enqueue_job(c,soldier_id=SOLDIER_ID,resource=RESOURCE,lane=LANE,priority_class='bootstrap',reason='phase3e_lifecycle_b',priority_value=0)
        q=c.execute(text("SELECT job_id,status,attempt_count,collector_uuid,lease_token,claimed_at,started_at,lease_expires_at FROM collection_jobs WHERE job_id=:j"),{'j':job_id}).mappings().one()
        if q['status']!='pending' or int(q['attempt_count'])!=0 or any(q[k] is not None for k in ('collector_uuid','lease_token','claimed_at','started_at','lease_expires_at')):
            raise RuntimeError("seeded Lifecycle B job has unexpected ownership state")
    print("===== BF4PS PHASE 3E LIFECYCLE B SINGLE-JOB SEED =====")
    print(f"soldier: {SOLDIER_ID} {CURRENT_NAME!r} persona={PERSONA_ID} platform={PLATFORM}")
    print(f"job:     {job_id}")
    print("status:  pending")
    print("attempt: 0")
    print("Battlelog requests: 0")
    print("LIFECYCLE B SEED: PASS")
    return 0

if __name__=='__main__': raise SystemExit(main())
