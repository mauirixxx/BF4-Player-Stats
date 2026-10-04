#!/usr/bin/env python3
"""Read-only final reconciliation for Lifecycle A."""
import argparse,os,sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit
from sqlalchemy import create_engine,text
sys.path.insert(0,str(Path(__file__).resolve().parent))
from phase3e_lifecycle_a_common import *

def main()->int:
 ap=argparse.ArgumentParser(); ap.add_argument('--drain-event-id',type=int,required=True); ap.add_argument('--undrain-event-id',type=int,required=True); a=ap.parse_args()
 if a.undrain_event_id<a.drain_event_id: raise SystemExit('REFUSING: undrain boundary precedes drain boundary')
 url=os.environ.get('BF4PS_DATABASE_URL'); p=urlsplit(url or '')
 if not url or p.hostname!=EXPECTED_DB_HOST or p.path.lstrip('/')!=EXPECTED_DATABASE: print('REFUSING: wrong database target'); return 2
 e=create_engine(url,pool_pre_ping=True); ids=list(COHORT_SOLDIER_IDS); target=HOSTS[TARGET_HOST]
 with e.connect() as c:
  assert_target(c)
  events=c.execute(text("SELECT event_id,collector_uuid,hostname_snapshot,egress_key_snapshot,soldier_id,platform,event_type,attempt_number FROM collection_events WHERE resource='detailed' AND lane='background' AND soldier_id=ANY(:ids) AND event_type IN ('collection_success','collection_failure') ORDER BY event_id"),{'ids':ids}).mappings().all()
  foreign=int(c.execute(text("SELECT count(*) FROM collection_events WHERE resource='detailed' AND lane='background' AND soldier_id IS NOT NULL AND soldier_id<>ALL(:ids) AND collector_uuid=ANY(:uuids)"),{'ids':ids,'uuids':list(FROZEN_UUIDS)}).scalar_one())
  queue=int(c.execute(text("SELECT count(*) FROM collection_jobs WHERE resource='detailed' AND lane='background' AND soldier_id=ANY(:ids)"),{'ids':ids}).scalar_one())
  collectors=c.execute(text("SELECT collector_uuid,hostname,egress_key,drained,current_job_id,heartbeat_state FROM collectors WHERE collector_uuid=ANY(:uuids)"),{'uuids':list(FROZEN_UUIDS)}).mappings().all()
 terminal=[r for r in events]; per=Counter(r['collector_uuid'] for r in terminal); soldiers=Counter(int(r['soldier_id']) for r in terminal)
 target_during=[r for r in terminal if r['collector_uuid']==target.collector_uuid and a.drain_event_id < int(r['event_id']) <= a.undrain_event_id]
 target_after=[r for r in terminal if r['collector_uuid']==target.collector_uuid and int(r['event_id'])>a.undrain_event_id]
 survivor_during=[r for r in terminal if r['collector_uuid']!=target.collector_uuid and a.drain_event_id < int(r['event_id']) <= a.undrain_event_id]
 identities=all(r['collector_uuid'] in FROZEN_UUIDS and r['hostname_snapshot'] in HOSTS and r['egress_key_snapshot']==HOSTS[r['hostname_snapshot']].egress_key for r in terminal)
 checks={'exactly 360 terminal attempts':len(terminal)==360,'each frozen soldier exactly once':len(soldiers)==360 and all(v==1 for v in soldiers.values()),'all three progressed':all(per[h.collector_uuid]>0 for h in HOSTS.values()),'target no terminal work while drained':not target_during,'survivors progressed while target drained':len(survivor_during)>0,'target progressed after explicit undrain':len(target_after)>0,'event identity snapshots exact':identities,'no frozen-collector work outside cohort':foreign==0,'Lifecycle A queue converged':queue==0,'collectors own no current job':all(r['current_job_id'] is None for r in collectors)}
 print('===== BF4PS PHASE 3E LIFECYCLE A RECONCILIATION =====')
 print(f'drain boundary event_id:   {a.drain_event_id}\nundrain boundary event_id: {a.undrain_event_id}')
 for host,h in HOSTS.items(): print(f'{host:<8} terminal={per[h.collector_uuid]}')
 for k,v in checks.items(): print(f'{k:<45} {"PASS" if v else "FAIL"}')
 ok=all(checks.values()); print(f'\nLIFECYCLE A RECONCILIATION: {"PASS" if ok else "FAIL"}'); return 0 if ok else 1
if __name__=='__main__':sys.exit(main())
