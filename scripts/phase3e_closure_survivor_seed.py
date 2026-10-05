#!/usr/bin/env python3
"""Seed exactly three pristine jobs for Phase 3E survivor-progress closure."""
from sqlalchemy import create_engine, text
from bf4ps.collection_jobs import enqueue_job
from phase3e_lifecycle_b_common import database_url, assert_target, RESOURCE, LANE
from phase3e_closure_survivor_cohort import COHORT


def main()->int:
    e=create_engine(database_url(),pool_pre_ping=True)
    seeded=[]
    with e.begin() as c:
        assert_target(c)
        for soldier_id,persona_id,platform,current_name in COHORT:
            row=c.execute(text("""
                SELECT s.persona_id,s.platform,s.current_name,
                       cs.detailed_state,cs.detailed_last_attempt_at,cs.detailed_last_success_at,
                       cs.detailed_next_due_at,cs.detailed_consecutive_failures,
                       cs.detailed_last_error_class,cs.detailed_last_error_message
                FROM soldiers s JOIN collection_state cs USING (soldier_id)
                WHERE s.soldier_id=:sid FOR UPDATE OF cs
            """),{'sid':soldier_id}).mappings().one_or_none()
            if row is None or (int(row['persona_id']),row['platform'],row['current_name'])!=(persona_id,platform,current_name):
                raise RuntimeError(f"frozen soldier identity drift: {soldier_id}")
            pristine=(row['detailed_state']=='never_attempted' and row['detailed_last_attempt_at'] is None
                      and row['detailed_last_success_at'] is None and row['detailed_next_due_at'] is None
                      and int(row['detailed_consecutive_failures'])==0
                      and row['detailed_last_error_class'] is None and row['detailed_last_error_message'] is None)
            if not pristine: raise RuntimeError(f"soldier {soldier_id} is no longer pristine")
            existing=c.execute(text("SELECT job_id FROM collection_jobs WHERE soldier_id=:sid AND resource=:r"),{'sid':soldier_id,'r':RESOURCE}).scalar_one_or_none()
            if existing is not None: raise RuntimeError(f"soldier {soldier_id} already has detailed job {existing}")
        for soldier_id,persona_id,platform,current_name in COHORT:
            job_id=enqueue_job(c,soldier_id=soldier_id,resource=RESOURCE,lane=LANE,priority_class='bootstrap',reason='phase3e_closure_survivor_progress',priority_value=0)
            q=c.execute(text("SELECT status,attempt_count,collector_uuid,lease_token,claimed_at,started_at,lease_expires_at FROM collection_jobs WHERE job_id=:j"),{'j':job_id}).mappings().one()
            if q['status']!='pending' or int(q['attempt_count'])!=0 or any(q[k] is not None for k in ('collector_uuid','lease_token','claimed_at','started_at','lease_expires_at')):
                raise RuntimeError(f"seeded job {job_id} has unexpected ownership state")
            seeded.append((job_id,soldier_id,current_name))
    print("===== BF4PS PHASE 3E SURVIVOR-PROGRESS SEED =====")
    for job_id,soldier_id,current_name in seeded:
        print(f"job={job_id} soldier={soldier_id} name={current_name!r} status=pending attempt=0")
    print("Battlelog requests: 0")
    print("SURVIVOR-PROGRESS SEED: PASS")
    return 0

if __name__=='__main__': raise SystemExit(main())
