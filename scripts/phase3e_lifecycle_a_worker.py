#!/usr/bin/env python3
"""Drain-aware sustained worker for Phase 3E Lifecycle A."""
import os,signal,socket,sys,time
from pathlib import Path
from urllib.parse import urlsplit
from sqlalchemy import create_engine,text
sys.path.insert(0,str(Path(__file__).resolve().parent))
from phase3e_lifecycle_a_common import *
from bf4ps.bounded_feeder import replenish_detailed_bootstrap
from bf4ps.collector_runtime import heartbeat_collector,register_collector,stop_collector
from bf4ps.detailed_collector import CollectorIdentity,CollectedJob,FailedJob,collect_one_detailed_job
STOP=False
def stop(*_):
 global STOP; STOP=True

def terminal(c): return int(c.execute(text("SELECT count(*) FROM collection_events WHERE resource='detailed' AND lane='background' AND soldier_id=ANY(:ids) AND event_type IN ('collection_success','collection_failure')"),{'ids':list(COHORT_SOLDIER_IDS)}).scalar_one())
def safety(c):
 assert_target(c); ids=list(COHORT_SOLDIER_IDS)
 foreign=int(c.execute(text("SELECT count(*) FROM collection_jobs WHERE resource='detailed' AND lane='background' AND soldier_id<>ALL(:ids)"),{'ids':ids}).scalar_one())
 bad=int(c.execute(text("SELECT count(*) FROM collection_jobs WHERE resource='detailed' AND lane='background' AND soldier_id=ANY(:ids) AND status IN ('claimed','running') AND collector_uuid<>ALL(:uuids)"),{'ids':ids,'uuids':list(FROZEN_UUIDS)}).scalar_one())
 n=terminal(c)
 if foreign or bad or n>GLOBAL_ATTEMPT_CEILING: raise RuntimeError(f'safety boundary failed foreign={foreign} bad_owner={bad} terminal={n}')
 return n

def main()->None:
 host=socket.gethostname().split('.',1)[0]; frozen=HOSTS.get(host)
 if not frozen: raise SystemExit(f'REFUSING: host {host!r} not frozen')
 url=os.environ.get('BF4PS_DATABASE_URL'); p=urlsplit(url or '')
 if not url or p.hostname!=EXPECTED_DB_HOST or p.path.lstrip('/')!=EXPECTED_DATABASE: raise SystemExit('REFUSING: wrong database target')
 ident=CollectorIdentity(frozen.collector_uuid,frozen.collector_name,host,frozen.egress_key,'background'); e=create_engine(url,pool_pre_ping=True)
 with e.begin() as c: safety(c); control=register_collector(c,identity=ident,software_version='phase3e-lifecycle-a')
 print(f'===== LIFECYCLE A WORKER {host} =====\nUUID: {frozen.collector_uuid}\ninitial drained: {control.drained}',flush=True)
 signal.signal(signal.SIGTERM,stop); signal.signal(signal.SIGINT,stop); was_drained=None; local=0
 try:
  while not STOP:
   with e.begin() as c:
    n=safety(c); control=heartbeat_collector(c,collector_uuid=frozen.collector_uuid,software_version='phase3e-lifecycle-a')
    if control.may_claim and n<GLOBAL_ATTEMPT_CEILING:
     replenish_detailed_bootstrap(c,target_depth=TARGET_DEPTH,max_soldier_id=max(COHORT_SOLDIER_IDS),allowed_soldier_ids=COHORT_SOLDIER_IDS,max_total_attempts=GLOBAL_ATTEMPT_CEILING)
   if control.drained!=was_drained:
    print(f'CONTROL BOUNDARY drained={control.drained} terminal={n}',flush=True); was_drained=control.drained
   if not control.enabled: print('collector disabled; clean stop',flush=True); break
   if n>=GLOBAL_ATTEMPT_CEILING: print('global attempt ceiling reached',flush=True); break
   if control.drained: time.sleep(1); continue
   out=collect_one_detailed_job(e,identity=ident,request_interval_seconds=REQUEST_INTERVAL_SECONDS,lease_seconds=LEASE_SECONDS,timeout_seconds=15,retry_after_seconds=300,allowed_soldier_ids=COHORT_SOLDIER_IDS,max_total_attempts=GLOBAL_ATTEMPT_CEILING)
   if out is None: time.sleep(.5); continue
   local+=1
   if isinstance(out,CollectedJob): print(f'[{local:03d}] SUCCESS soldier={out.soldier_id} job={out.job_id} {out.platform}',flush=True)
   elif isinstance(out,FailedJob):
    print(f'[{local:03d}] FAILURE soldier={out.soldier_id} job={out.job_id} http={out.http_status} class={out.error_class}',flush=True)
    if out.http_status in {403,429} or out.error_class=='battlelog_throttle': print('THROTTLE SIGNAL; stopping',flush=True); break
 finally:
  with e.begin() as c: stop_collector(c,collector_uuid=frozen.collector_uuid)
 print(f'LIFECYCLE A WORKER STOPPED CLEANLY local_attempts={local}',flush=True)
if __name__=='__main__':main()
