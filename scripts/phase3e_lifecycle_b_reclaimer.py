#!/usr/bin/env python3
"""Lifecycle B reclaimer: prove kah-01 can fence an expired hnl-01 lease.

No Battlelog request is performed. The reclaimed attempt is intentionally left
running so the next checkpoint can test stale-token rejection before cleanup.
"""
from __future__ import annotations
import socket
from uuid import UUID
from sqlalchemy import create_engine, text
from bf4ps.collection_jobs import claim_next_job, mark_job_running
from bf4ps.collector_runtime import heartbeat_collector
from phase3e_lifecycle_b_common import *
from phase3e_lifecycle_b_cohort import SOLDIER_ID,PERSONA_ID,PLATFORM,CURRENT_NAME

JOB_ID=813
STALE_TOKEN=UUID("9ad8057a-57fe-4cdb-82fa-49fc58c4ea39")


def main()->int:
    host=socket.gethostname().split('.')[0]
    if host!=RECLAIMER_HOST:
        raise SystemExit(f"REFUSING: reclaimer must run on {RECLAIMER_HOST}, got {host}")
    e=create_engine(database_url(),pool_pre_ping=True)
    with e.begin() as c:
        assert_target(c)
        ctl=heartbeat_collector(c,collector_uuid=RECLAIMER_UUID,software_version='phase3e-lifecycle-b-reclaimer')
        if not ctl.may_claim:
            raise RuntimeError("reclaimer collector is disabled or drained")
        q=c.execute(text("""
            SELECT job_id,soldier_id,status,attempt_count,collector_uuid,lease_token,
                   claimed_at,started_at,lease_expires_at,(lease_expires_at <= now()) AS expired
            FROM collection_jobs WHERE job_id=:j FOR UPDATE
        """),{'j':JOB_ID}).mappings().one_or_none()
        if q is None:
            raise RuntimeError("Lifecycle B job 813 is missing")
        expected=(int(q['soldier_id'])==SOLDIER_ID and q['status']=='running' and int(q['attempt_count'])==1
                  and q['collector_uuid']==VICTIM_UUID and q['lease_token']==STALE_TOKEN and bool(q['expired']))
        if not expected:
            raise RuntimeError(f"unexpected abandoned victim state: {dict(q)}")
        stale_claimed=q['claimed_at']; stale_started=q['started_at']; stale_expiry=q['lease_expires_at']
        job=claim_next_job(c,collector_uuid=RECLAIMER_UUID,lane=LANE,resource=RESOURCE,
                           lease_seconds=LEASE_SECONDS,allowed_soldier_ids=(SOLDIER_ID,),max_total_attempts=2)
        if job is None or job.job_id!=JOB_ID or job.soldier_id!=SOLDIER_ID or job.attempt_count!=2:
            raise RuntimeError(f"exact expired job was not reclaimed as attempt 2: {job}")
        if job.lease_token==STALE_TOKEN:
            raise RuntimeError("fencing token did not rotate")
        if not mark_job_running(c,job):
            raise RuntimeError("reclaimer could not mark attempt 2 running")
        c.execute(text("UPDATE collectors SET current_job_id=:j, updated_at=now() WHERE collector_uuid=:u"),{'j':JOB_ID,'u':RECLAIMER_UUID})
    with e.connect() as c:
        q2=c.execute(text("""
            SELECT status,attempt_count,collector_uuid,lease_token,claimed_at,started_at,lease_expires_at
            FROM collection_jobs WHERE job_id=:j
        """),{'j':JOB_ID}).mappings().one()
        now=c.execute(text("SELECT now()")).scalar_one()
    ok=(q2['status']=='running' and int(q2['attempt_count'])==2 and q2['collector_uuid']==RECLAIMER_UUID
        and q2['lease_token']==job.lease_token and q2['lease_token']!=STALE_TOKEN)
    if not ok:
        raise RuntimeError(f"post-reclaim ownership verification failed: {dict(q2)}")
    print("===== BF4PS PHASE 3E LIFECYCLE B RECLAIMED =====")
    print(f"host:             {host}")
    print(f"job:              {JOB_ID}")
    print(f"soldier:          {SOLDIER_ID} {CURRENT_NAME!r} persona={PERSONA_ID} platform={PLATFORM}")
    print("stale attempt:    1")
    print(f"stale owner:      {VICTIM_UUID}")
    print(f"stale token:      {STALE_TOKEN}")
    print(f"stale claimed:    {stale_claimed}")
    print(f"stale started:    {stale_started}")
    print(f"stale expired:    {stale_expiry}")
    print("new attempt:      2")
    print(f"new owner:        {q2['collector_uuid']}")
    print(f"new token:        {q2['lease_token']}")
    print(f"new claimed:      {q2['claimed_at']}")
    print(f"new started:      {q2['started_at']}")
    print(f"new lease expiry: {q2['lease_expires_at']}")
    print(f"database now:     {now}")
    print("Battlelog requests: 0")
    print("LIFECYCLE B RECLAIM: PASS")
    return 0

if __name__=='__main__': raise SystemExit(main())
