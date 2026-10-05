#!/usr/bin/env python3
"""Read-only reconciliation for the Lifecycle A eight-job retry convergence."""
from __future__ import annotations
import os, sys
from pathlib import Path
from urllib.parse import urlsplit
from sqlalchemy import create_engine, text
sys.path.insert(0, str(Path(__file__).resolve().parent))
from phase3e_lifecycle_a_common import *  # noqa: E402,F403

RETRY_JOB_IDS=(765,766,768,769,770,771,772,773)
RETRY_SOLDIER_IDS=(8693,8694,8696,8697,8698,8699,8700,8701)
EXPECTED_RETRY_COLLECTOR=HOSTS['tcou']


def main()->int:
 url=os.environ.get('BF4PS_DATABASE_URL'); p=urlsplit(url or '')
 if not url or p.hostname!=EXPECTED_DB_HOST or p.path.lstrip('/')!=EXPECTED_DATABASE:
  print('REFUSING: wrong database target'); return 2
 engine=create_engine(url,pool_pre_ping=True)
 with engine.connect() as c:
  assert_target(c)
  events=c.execute(text("""
   SELECT event_id,collector_uuid,collector_name_snapshot,hostname_snapshot,egress_key_snapshot,
          job_id,soldier_id,platform,event_type,attempt_number,result,http_status,error_class
   FROM collection_events
   WHERE resource='detailed' AND lane='background'
     AND job_id=ANY(:jobs) AND attempt_number=2
     AND event_type IN ('collection_success','collection_failure')
   ORDER BY event_id
  """),{'jobs':list(RETRY_JOB_IDS)}).mappings().all()
  queue=c.execute(text("""
   SELECT job_id,soldier_id,status,attempt_count,collector_uuid,lease_token,claimed_at,started_at,lease_expires_at
   FROM collection_jobs WHERE job_id=ANY(:jobs) ORDER BY job_id
  """),{'jobs':list(RETRY_JOB_IDS)}).mappings().all()
  states=c.execute(text("""
   SELECT soldier_id,detailed_state,detailed_last_attempt_at,detailed_last_success_at,
          detailed_consecutive_failures,detailed_last_error_class,detailed_last_error_message
   FROM collection_state WHERE soldier_id=ANY(:ids) ORDER BY soldier_id
  """),{'ids':list(RETRY_SOLDIER_IDS)}).mappings().all()
  current=c.execute(text("SELECT soldier_id,source_fetched_at FROM detailed_stats_current WHERE soldier_id=ANY(:ids) ORDER BY soldier_id"),{'ids':list(RETRY_SOLDIER_IDS)}).mappings().all()
  third=int(c.execute(text("""
   SELECT count(*) FROM collection_events
   WHERE resource='detailed' AND lane='background' AND job_id=ANY(:jobs)
     AND attempt_number>2 AND event_type IN ('collection_success','collection_failure')
  """),{'jobs':list(RETRY_JOB_IDS)}).scalar_one())
  foreign=int(c.execute(text("""
   SELECT count(*) FROM collection_events
   WHERE resource='detailed' AND lane='background' AND attempt_number=2
     AND collector_uuid=:uuid AND job_id<>ALL(:jobs)
     AND event_type IN ('collection_success','collection_failure')
  """),{'uuid':EXPECTED_RETRY_COLLECTOR.collector_uuid,'jobs':list(RETRY_JOB_IDS)}).scalar_one())
 expected=dict(zip(RETRY_JOB_IDS,RETRY_SOLDIER_IDS,strict=True))
 identities=all(
  r['collector_uuid']==EXPECTED_RETRY_COLLECTOR.collector_uuid
  and r['collector_name_snapshot']==EXPECTED_RETRY_COLLECTOR.collector_name
  and r['hostname_snapshot']=='tcou'
  and r['egress_key_snapshot']==EXPECTED_RETRY_COLLECTOR.egress_key for r in events)
 checks={
  'exactly eight attempt-two terminal events':len(events)==8,
  'all eight attempt-two events successful':len(events)==8 and all(r['event_type']=='collection_success' for r in events),
  'exact retry jobs and soldiers covered':len(events)==8 and {int(r['job_id']):int(r['soldier_id']) for r in events}==expected,
  'all retries remained PS4':len(events)==8 and all(r['platform']=='ps4' for r in events),
  'retry collector identity exact':identities,
  'no HTTP/throttle/error evidence on retries':len(events)==8 and all(r['http_status'] not in (403,429) and r['error_class'] is None for r in events),
  'no third-or-later terminal attempts':third==0,
  'no foreign attempt-two work by retry collector':foreign==0,
  'authorized retry queue fully converged':len(queue)==0,
  'eight collection-state rows present':len(states)==8,
  'all retry soldiers detailed-success':len(states)==8 and all(r['detailed_state']=='success' and int(r['detailed_consecutive_failures'])==0 and r['detailed_last_success_at'] is not None and r['detailed_last_error_class'] is None and r['detailed_last_error_message'] is None for r in states),
  'all retry soldiers have detailed current rows':len(current)==8 and all(r['source_fetched_at'] is not None for r in current),
 }
 print('===== BF4PS PHASE 3E LIFECYCLE A RETRY RECONCILIATION =====')
 print(f'attempt-two terminal events: {len(events)}/8')
 print(f'residual authorized queue:   {len(queue)}')
 print(f'third-or-later terminals:    {third}')
 print(f'foreign retry work:          {foreign}')
 if events: print(f'retry event span:            {events[0]["event_id"]}..{events[-1]["event_id"]}')
 for r in events: print(f'job={r["job_id"]:<4} soldier={r["soldier_id"]:<5} event={r["event_id"]:<5} {r["event_type"]}')
 print('\n===== VALIDATION =====')
 for k,v in checks.items(): print(f'{k:<52} {"PASS" if v else "FAIL"}')
 ok=all(checks.values())
 print(f'\nLIFECYCLE A RETRY RECONCILIATION: {"PASS" if ok else "FAIL"}')
 print('database writes: 0')
 print('Battlelog requests: 0')
 return 0 if ok else 1

if __name__=='__main__': sys.exit(main())
