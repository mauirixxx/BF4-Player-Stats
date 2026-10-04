#!/usr/bin/env python3
"""Seed exactly one production bounded-feeder pass for Lifecycle A."""
import os,sys
from pathlib import Path
from urllib.parse import urlsplit
from sqlalchemy import create_engine,text
sys.path.insert(0,str(Path(__file__).resolve().parent))
from phase3e_lifecycle_a_common import *
from bf4ps.bounded_feeder import replenish_detailed_bootstrap

def main()->int:
 url=os.environ.get('BF4PS_DATABASE_URL'); p=urlsplit(url or '')
 if not url or p.hostname!=EXPECTED_DB_HOST or p.path.lstrip('/')!=EXPECTED_DATABASE: print('REFUSING: wrong database target'); return 2
 e=create_engine(url,pool_pre_ping=True); ids=list(COHORT_SOLDIER_IDS)
 with e.begin() as c:
  assert_target(c)
  terminal=int(c.execute(text("SELECT count(*) FROM collection_events WHERE resource='detailed' AND lane='background' AND soldier_id=ANY(:ids) AND event_type IN ('collection_success','collection_failure')"),{'ids':ids}).scalar_one())
  queued=int(c.execute(text("SELECT count(*) FROM collection_jobs WHERE resource='detailed' AND lane='background' AND soldier_id=ANY(:ids)"),{'ids':ids}).scalar_one())
  foreign=int(c.execute(text("SELECT count(*) FROM collection_jobs WHERE resource='detailed' AND lane='background' AND soldier_id<>ALL(:ids)"),{'ids':ids}).scalar_one())
  if terminal or queued or foreign: print(f'REFUSING: terminal={terminal} queued={queued} foreign={foreign}'); return 1
  r=replenish_detailed_bootstrap(c,target_depth=TARGET_DEPTH,max_soldier_id=max(ids),allowed_soldier_ids=ids,max_total_attempts=GLOBAL_ATTEMPT_CEILING)
 ok=r.created==TARGET_DEPTH and r.actionable_after==TARGET_DEPTH
 print('===== LIFECYCLE A INITIAL BOUNDED SEED ====='); print(f'created: {r.created}\nactionable: {r.actionable_after}\ntarget: {TARGET_DEPTH}\nRESULT: {"PASS" if ok else "FAIL"}')
 return 0 if ok else 1
if __name__=='__main__':sys.exit(main())
