#!/usr/bin/env python3
"""Lifecycle B victim: claim the frozen job, mark running, then wait to be killed.

No Battlelog request is performed. The process intentionally does not renew or
cleanly release its lease; the operator terminates it after the kill banner.
"""
from __future__ import annotations
import socket, time
from sqlalchemy import create_engine, text
from bf4ps.collection_jobs import claim_next_job, mark_job_running
from bf4ps.collector_runtime import heartbeat_collector
from phase3e_lifecycle_b_common import *
from phase3e_lifecycle_b_cohort import SOLDIER_ID,PERSONA_ID,PLATFORM,CURRENT_NAME

def main()->int:
    host=socket.gethostname().split('.')[0]
    if host!=VICTIM_HOST: raise SystemExit(f"REFUSING: victim must run on {VICTIM_HOST}, got {host}")
    e=create_engine(database_url(),pool_pre_ping=True)
    with e.begin() as c:
        assert_target(c)
        ctl=heartbeat_collector(c,collector_uuid=VICTIM_UUID,software_version='phase3e-lifecycle-b-victim')
        if not ctl.may_claim: raise RuntimeError("victim collector is disabled or drained")
        row=c.execute(text("SELECT job_id,status,attempt_count,collector_uuid FROM collection_jobs WHERE soldier_id=:sid AND resource=:r FOR UPDATE"),{'sid':SOLDIER_ID,'r':RESOURCE}).mappings().one_or_none()
        if row is None or row['status']!='pending' or int(row['attempt_count'])!=0 or row['collector_uuid'] is not None:
            raise RuntimeError(f"unexpected pre-claim Lifecycle B queue state: {row}")
        job=claim_next_job(c,collector_uuid=VICTIM_UUID,lane=LANE,resource=RESOURCE,lease_seconds=LEASE_SECONDS,allowed_soldier_ids=(SOLDIER_ID,),max_total_attempts=2)
        if job is None or job.soldier_id!=SOLDIER_ID: raise RuntimeError("victim did not claim exact frozen job")
        if not mark_job_running(c,job): raise RuntimeError("victim could not mark frozen job running")
        c.execute(text("UPDATE collectors SET current_job_id=:j, updated_at=now() WHERE collector_uuid=:u"),{'j':job.job_id,'u':VICTIM_UUID})
    with e.connect() as c:
        q=c.execute(text("SELECT status,attempt_count,collector_uuid,lease_token,claimed_at,started_at,lease_expires_at FROM collection_jobs WHERE job_id=:j"),{'j':job.job_id}).mappings().one()
        now=c.execute(text("SELECT now()")).scalar_one()
    if q['status']!='running' or int(q['attempt_count'])!=1 or q['collector_uuid']!=VICTIM_UUID or q['lease_token']!=job.lease_token:
        raise RuntimeError("post-claim ownership verification failed")
    print("===== BF4PS PHASE 3E LIFECYCLE B VICTIM ARMED =====",flush=True)
    print(f"host:          {host}",flush=True)
    print(f"job:           {job.job_id}",flush=True)
    print(f"soldier:       {SOLDIER_ID} {CURRENT_NAME!r} persona={PERSONA_ID} platform={PLATFORM}",flush=True)
    print(f"attempt:       {job.attempt_count}",flush=True)
    print(f"lease token:   {job.lease_token}",flush=True)
    print(f"claimed at:    {q['claimed_at']}",flush=True)
    print(f"started at:    {q['started_at']}",flush=True)
    print(f"lease expires: {q['lease_expires_at']}",flush=True)
    print(f"database now:  {now}",flush=True)
    print("Battlelog requests: 0",flush=True)
    print("lease renewal: NONE",flush=True)
    print("clean release: NONE",flush=True)
    print("",flush=True)
    print("=====================================================",flush=True)
    print("===== KILL HNL-01 COLLECTOR NOW (Ctrl-C / kill) =====",flush=True)
    print("=====================================================",flush=True)
    while True: time.sleep(60)

if __name__=='__main__': raise SystemExit(main())
