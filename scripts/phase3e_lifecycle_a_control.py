#!/usr/bin/env python3
"""Explicit operator control/status tool for Lifecycle A target collector."""
import argparse,os,sys
from pathlib import Path
from urllib.parse import urlsplit
from sqlalchemy import create_engine,text
sys.path.insert(0,str(Path(__file__).resolve().parent))
from phase3e_lifecycle_a_common import *

def main()->int:
 ap=argparse.ArgumentParser(); ap.add_argument('action',choices=('status','drain','undrain')); a=ap.parse_args()
 url=os.environ.get('BF4PS_DATABASE_URL'); p=urlsplit(url or '')
 if not url or p.hostname!=EXPECTED_DB_HOST or p.path.lstrip('/')!=EXPECTED_DATABASE: print('REFUSING: wrong database target'); return 2
 e=create_engine(url,pool_pre_ping=True); target=HOSTS[TARGET_HOST]; ids=list(COHORT_SOLDIER_IDS)
 ctx=e.connect() if a.action=='status' else e.begin()
 with ctx as c:
  assert_target(c)
  if a.action!='status':
   value=a.action=='drain'; result=c.execute(text("UPDATE collectors SET drained=:value,updated_at=now() WHERE collector_uuid=:uuid AND retired_at IS NULL"),{'value':value,'uuid':target.collector_uuid})
   if result.rowcount!=1: raise RuntimeError('target collector missing or retired')
  row=c.execute(text("SELECT collector_uuid,collector_name,hostname,enabled,drained,heartbeat_state,current_job_id,last_heartbeat_at,started_at FROM collectors WHERE collector_uuid=:uuid"),{'uuid':target.collector_uuid}).mappings().one()
  boundary=int(c.execute(text("SELECT COALESCE(MAX(event_id),0) FROM collection_events WHERE resource='detailed' AND lane='background' AND soldier_id=ANY(:ids)"),{'ids':ids}).scalar_one())
  terminal=int(c.execute(text("SELECT count(*) FROM collection_events WHERE resource='detailed' AND lane='background' AND soldier_id=ANY(:ids) AND event_type IN ('collection_success','collection_failure')"),{'ids':ids}).scalar_one())
 print('===== LIFECYCLE A TARGET CONTROL ====='); print(f'action: {a.action}\nevent_id boundary: {boundary}\nterminal attempts: {terminal}/360')
 for k,v in row.items(): print(f'{k}: {v}')
 if a.action in ('drain','undrain'): print(f'RECORD THIS {a.action.upper()} EVENT-ID BOUNDARY: {boundary}')
 return 0
if __name__=='__main__':sys.exit(main())
