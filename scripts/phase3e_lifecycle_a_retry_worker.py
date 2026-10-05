#!/usr/bin/env python3
"""Bounded retry worker for the eight Lifecycle A residual jobs."""
from __future__ import annotations
import os, signal, socket, sys, time
from pathlib import Path
from urllib.parse import urlsplit
from sqlalchemy import create_engine, text
sys.path.insert(0, str(Path(__file__).resolve().parent))
from phase3e_lifecycle_a_common import *
from bf4ps.collector_runtime import heartbeat_collector, register_collector, stop_collector
from bf4ps.detailed_collector import CollectorIdentity, CollectedJob, FailedJob, collect_one_detailed_job

RETRY_JOB_IDS=(765,766,768,769,770,771,772,773)
RETRY_SOLDIER_IDS=(8693,8694,8696,8697,8698,8699,8700,8701)
STOP=False

def stop(*_):
 global STOP; STOP=True

def retry_terminals(c):
 return int(c.execute(text("SELECT count(*) FROM collection_events WHERE resource='detailed' AND lane='background' AND job_id=ANY(:jobs) AND event_type IN ('collection_success','collection_failure') AND attempt_number=2"),{'jobs':list(RETRY_JOB_IDS)}).scalar_one())

def safety(c):
 assert_target(c)
 rows=c.execute(text("SELECT job_id,soldier_id,status,attempt_count,collector_uuid,lease_token,claimed_at,started_at,lease_expires_at FROM collection_jobs WHERE job_id=ANY(:jobs) ORDER BY job_id"),{'jobs':list(RETRY_JOB_IDS)}).mappings().all()
 expected=dict(zip(RETRY_JOB_IDS,RETRY_SOLDIER_IDS,strict=True))
 for r in rows:
  jid=int(r['job_id'])
  if jid not in expected or int(r['soldier_id'])!=expected[jid]: raise RuntimeError(f'identity mismatch job={jid}')
  if r['status']=='pending':
   if int(r['attempt_count']) not in {1,2}: raise RuntimeError(f'unexpected attempt count job={jid}')
   if any(r[k] is not None for k in ('collector_uuid','lease_token','claimed_at','started_at','lease_expires_at')): raise RuntimeError(f'pending job owns lease job={jid}')
  elif r['status'] in {'claimed','running'}:
   if r['collector_uuid'] not in FROZEN_UUIDS: raise RuntimeError(f'foreign owner job={jid}')
  else: raise RuntimeError(f'unexpected status job={jid}: {r["status"]}')
 n=retry_terminals(c)
 if n>8: raise RuntimeError(f'retry ceiling exceeded: {n}')
 # Successful collection finalizes/deletes its queue row.  The durable event
 # ledger is therefore the authority for completed retry jobs; only unresolved
 # retries are expected to remain in collection_jobs.
 if len(rows)+n != 8:
  raise RuntimeError(f'retry accounting mismatch: queue_rows={len(rows)} attempt2_terminals={n} expected=8')
 return n

def main():
 host=socket.gethostname().split('.',1)[0]; frozen=HOSTS.get(host)
 if not frozen: raise SystemExit(f'REFUSING: host {host!r} not frozen')
 url=os.environ.get('BF4PS_DATABASE_URL'); p=urlsplit(url or '')
 if not url or p.hostname!=EXPECTED_DB_HOST or p.path.lstrip('/')!=EXPECTED_DATABASE: raise SystemExit('REFUSING: wrong database target')
 e=create_engine(url,pool_pre_ping=True); ident=CollectorIdentity(frozen.collector_uuid,frozen.collector_name,host,frozen.egress_key,'background')
 with e.begin() as c:
  n=safety(c); control=register_collector(c,identity=ident,software_version='phase3e-lifecycle-a-retry')
  if not control.enabled or control.drained: raise RuntimeError(f'collector not eligible enabled={control.enabled} drained={control.drained}')
  pending=int(c.execute(text("SELECT count(*) FROM collection_jobs WHERE job_id=ANY(:jobs) AND status='pending' AND attempt_count=1"),{'jobs':list(RETRY_JOB_IDS)}).scalar_one())
  if n==0 and pending!=8: raise RuntimeError(f'expected eight untouched retries; found {pending}')
 print(f'===== LIFECYCLE A RETRY WORKER {host} =====\nUUID: {frozen.collector_uuid}\nauthorized jobs: {RETRY_JOB_IDS}',flush=True)
 signal.signal(signal.SIGTERM,stop); signal.signal(signal.SIGINT,stop); local=0
 try:
  while not STOP:
   with e.begin() as c:
    n=safety(c); control=heartbeat_collector(c,collector_uuid=frozen.collector_uuid,software_version='phase3e-lifecycle-a-retry')
   if not control.enabled or control.drained: print('operator control stop',flush=True); break
   if n>=8: print('retry terminal ceiling reached',flush=True); break
   out=collect_one_detailed_job(e,identity=ident,request_interval_seconds=REQUEST_INTERVAL_SECONDS,lease_seconds=LEASE_SECONDS,timeout_seconds=15,retry_after_seconds=300,allowed_soldier_ids=RETRY_SOLDIER_IDS,max_total_attempts=368)
   if out is None: time.sleep(.5); continue
   local+=1
   if out.job_id not in RETRY_JOB_IDS or out.soldier_id not in RETRY_SOLDIER_IDS: raise RuntimeError(f'unauthorized work job={out.job_id} soldier={out.soldier_id}')
   if isinstance(out,CollectedJob): print(f'[{local:02d}] SUCCESS soldier={out.soldier_id} job={out.job_id} {out.platform}',flush=True)
   elif isinstance(out,FailedJob):
    print(f'[{local:02d}] FAILURE soldier={out.soldier_id} job={out.job_id} http={out.http_status} class={out.error_class}',flush=True)
    if out.http_status in {403,429} or out.error_class=='battlelog_throttle': print('THROTTLE SIGNAL; stopping',flush=True); break
 finally:
  with e.begin() as c: stop_collector(c,collector_uuid=frozen.collector_uuid)
 print(f'LIFECYCLE A RETRY WORKER STOPPED CLEANLY local_attempts={local}',flush=True)
 return 0

if __name__=='__main__': sys.exit(main())
