#!/usr/bin/env python3
"""Lifecycle B controlled attempt-three completion on kah-01.

The deliberately expired attempt-two lease is reclaimed through the production
collector path. Exactly the frozen soldier is eligible; at most one Battlelog
request is authorized. Normal request gating, fetch, normalization, persistence,
event recording, and queue finalization are used.
"""
from __future__ import annotations
import socket
from sqlalchemy import create_engine, text
from bf4ps.collector_runtime import heartbeat_collector
from bf4ps.detailed_collector import CollectorIdentity, CollectedJob, FailedJob, collect_one_detailed_job
from phase3e_lifecycle_b_common import *
from phase3e_lifecycle_b_cohort import SOLDIER_ID,PERSONA_ID,PLATFORM,CURRENT_NAME

JOB_ID=813


def main()->int:
    host=socket.gethostname().split('.')[0]
    if host!=RECLAIMER_HOST: raise SystemExit(f"REFUSING: completion must run on {RECLAIMER_HOST}, got {host}")
    e=create_engine(database_url(),pool_pre_ping=True)
    with e.begin() as c:
        assert_target(c)
        ctl=heartbeat_collector(c,collector_uuid=RECLAIMER_UUID,software_version='phase3e-lifecycle-b-complete')
        if not ctl.may_claim: raise RuntimeError("reclaimer collector is disabled or drained")
        q=c.execute(text("""
            SELECT job_id,soldier_id,status,attempt_count,collector_uuid,lease_token,
                   lease_expires_at,(lease_expires_at <= now()) AS expired
            FROM collection_jobs WHERE job_id=:j
        """),{'j':JOB_ID}).mappings().one_or_none()
        if q is None: raise RuntimeError("Lifecycle B job 813 is missing")
        expected=(int(q['soldier_id'])==SOLDIER_ID and q['status']=='running' and int(q['attempt_count'])==2
                  and q['collector_uuid']==RECLAIMER_UUID and bool(q['expired']))
        if not expected: raise RuntimeError(f"unexpected pre-completion state: {dict(q)}")
        identity=c.execute(text("SELECT collector_name,hostname,egress_key,lane FROM collectors WHERE collector_uuid=:u"),{'u':RECLAIMER_UUID}).mappings().one()
    ci=CollectorIdentity(collector_uuid=RECLAIMER_UUID,collector_name=identity['collector_name'],hostname=identity['hostname'],egress_key=identity['egress_key'],lane=identity['lane'])
    print("===== BF4PS PHASE 3E LIFECYCLE B CONTROLLED COMPLETION =====",flush=True)
    print(f"host: {host} job={JOB_ID} soldier={SOLDIER_ID} {CURRENT_NAME!r}",flush=True)
    print("expected reclaim: attempt 3",flush=True)
    print("authorized Battlelog requests: at most 1",flush=True)
    result=collect_one_detailed_job(e,identity=ci,request_interval_seconds=5.0,lease_seconds=120,timeout_seconds=15.0,retry_after_seconds=300,allowed_soldier_ids=(SOLDIER_ID,),max_total_attempts=3)
    if result is None: raise RuntimeError("production collector did not reclaim Lifecycle B job")
    if result.job_id!=JOB_ID or result.soldier_id!=SOLDIER_ID: raise RuntimeError(f"foreign job collected: {result}")
    if isinstance(result,FailedJob):
        raise RuntimeError(f"Lifecycle B attempt 3 source failure: class={result.error_class} http={result.http_status}")
    if not isinstance(result,CollectedJob): raise RuntimeError(f"unexpected collector result: {result}")
    with e.begin() as c:
        remaining=c.execute(text("SELECT count(*) FROM collection_jobs WHERE job_id=:j"),{'j':JOB_ID}).scalar_one()
        ev=c.execute(text("""
            SELECT event_id,attempt_number,event_type,result,http_status,collector_uuid,lease_token
            FROM collection_events WHERE job_id=:j ORDER BY event_id DESC LIMIT 1
        """),{'j':JOB_ID}).mappings().one()
        state=c.execute(text("SELECT detailed_state,detailed_last_success_at,detailed_last_error_class FROM collection_state WHERE soldier_id=:s"),{'s':SOLDIER_ID}).mappings().one()
        current=c.execute(text("SELECT source_fetched_at FROM detailed_stats_current WHERE soldier_id=:s"),{'s':SOLDIER_ID}).mappings().one_or_none()
        c.execute(text("UPDATE collectors SET current_job_id=NULL, updated_at=now() WHERE collector_uuid=:u AND current_job_id=:j"),{'u':RECLAIMER_UUID,'j':JOB_ID})
    if remaining!=0: raise RuntimeError("Lifecycle B job did not finalize")
    if int(ev['attempt_number'])!=3 or ev['event_type']!='collection_success' or ev['result']!='success' or ev['collector_uuid']!=RECLAIMER_UUID: raise RuntimeError(f"unexpected terminal event: {dict(ev)}")
    if state['detailed_state']!='success' or state['detailed_last_success_at'] is None or state['detailed_last_error_class'] is not None or current is None: raise RuntimeError("detailed success state/current row missing")
    print(f"terminal event: {ev['event_id']} attempt={ev['attempt_number']} http={ev['http_status']}")
    print(f"completion token: {ev['lease_token']}")
    print(f"history_appended: {result.history_appended}")
    print("queue finalized: PASS")
    print("detailed state/current: PASS")
    print("LIFECYCLE B CONTROLLED COMPLETION: PASS")
    return 0

if __name__=='__main__': raise SystemExit(main())
