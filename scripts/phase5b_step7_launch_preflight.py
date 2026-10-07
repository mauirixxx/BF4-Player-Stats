#!/usr/bin/env python3
"""Read-only launch preflight for seeded Phase 5B Step 7 endurance."""
from __future__ import annotations
import os
from urllib.parse import urlsplit
from sqlalchemy import create_engine,text
from bf4ps.phase5b_step7_endurance import (
 EXPECTED_DATABASE,EXPECTED_REVISION,FROZEN_UUIDS,GLOBAL_ATTEMPT_CEILING,HOSTS,
 INITIAL_JOB_COUNT,JOB_REASON,PRIORITY_CLASS,RESOURCES,RUN_MARKER_EVENT_TYPE,RUN_NUMBER,
 SOFTWARE_VERSION,
)
def main():
 url=os.environ.get("BF4PS_DATABASE_URL"); parsed=urlsplit(url or "")
 if not url or parsed.path.lstrip("/")!=EXPECTED_DATABASE: raise SystemExit("REFUSING: wrong/missing BF4PS_DATABASE_URL")
 engine=create_engine(url,pool_pre_ping=True)
 with engine.connect() as c:
  db=c.execute(text("SELECT current_database()")).scalar_one(); rev=c.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
  rec=bool(c.execute(text("SELECT pg_is_in_recovery()")).scalar_one()); ro=c.execute(text("SELECT current_setting('transaction_read_only')")).scalar_one()
  if db!=EXPECTED_DATABASE or rev!=EXPECTED_REVISION or rec or ro!="off": raise RuntimeError("target mismatch")
  rows=c.execute(text("SELECT event_id,metadata FROM collection_events WHERE event_type=:t AND metadata->>'run_number'=:n"),
   {"t":RUN_MARKER_EVENT_TYPE,"n":str(RUN_NUMBER)}).mappings().all()
  if len(rows)!=1: raise RuntimeError(f"marker count={len(rows)}")
  b=int(rows[0]["event_id"]); ids=[int(x) for x in rows[0]["metadata"]["cohort_soldier_ids"]]
  if len(ids)!=1296 or len(set(ids))!=1296: raise RuntimeError("invalid marker allowlist")
  shape=c.execute(text("""
   SELECT COUNT(*) total,COUNT(DISTINCT (soldier_id,resource)) pairs,
    COUNT(*) FILTER(WHERE lane='background' AND priority_class=:pc AND reason=:reason
     AND status='pending' AND attempt_count=0 AND collector_uuid IS NULL AND lease_token IS NULL
     AND claimed_at IS NULL AND started_at IS NULL AND lease_expires_at IS NULL) good
   FROM collection_jobs WHERE soldier_id=ANY(:ids) AND resource=ANY(:resources)
  """),{"ids":ids,"resources":list(RESOURCES),"pc":PRIORITY_CLASS,"reason":JOB_REASON}).mappings().one()
  foreign=int(c.execute(text("SELECT COUNT(*) FROM collection_jobs WHERE lane='background' AND NOT (soldier_id=ANY(:ids) AND resource=ANY(:r))"),
   {"ids":ids,"r":list(RESOURCES)}).scalar_one())
  attempts=int(c.execute(text("SELECT COUNT(*) FROM collection_events WHERE event_id>:b AND soldier_id=ANY(:ids) AND resource=ANY(:r) AND event_type='collection_attempt_started'"),
   {"b":b,"ids":ids,"r":list(RESOURCES)}).scalar_one())
  regs=c.execute(text("SELECT collector_uuid,collector_name,hostname,lane,egress_key,enabled,drained,current_job_id,retired_at,software_version,started_at FROM collectors WHERE collector_uuid=ANY(:u)"),
   {"u":list(FROZEN_UUIDS)}).mappings().all()
  if int(shape["total"])!=INITIAL_JOB_COUNT or int(shape["pairs"])!=INITIAL_JOB_COUNT or int(shape["good"])!=INITIAL_JOB_COUNT: raise RuntimeError(f"queue shape={dict(shape)}")
  if foreign or attempts: raise RuntimeError(f"foreign={foreign} attempts={attempts}")
  if len(regs)!=3: raise RuntimeError(f"collector rows={len(regs)}")
  by_uuid={str(r["collector_uuid"]):r for r in regs}
  for hostname,h in HOSTS.items():
   r=by_uuid.get(str(h.collector_uuid))
   if not r or r["collector_name"]!=h.collector_name or r["hostname"]!=hostname or r["lane"]!="background" or r["egress_key"]!=h.egress_key: raise RuntimeError(f"identity mismatch {hostname}")
   if not r["enabled"] or r["drained"] or r["current_job_id"] is not None or r["retired_at"] is not None: raise RuntimeError(f"collector not launch-ready {hostname}: {dict(r)}")
 engine.dispose()
 print("===== BF4PS PHASE 5B STEP 7 LAUNCH PREFLIGHT =====")
 print(f"database={db} revision={rev} primary_writable=yes run_marker_event_id={b}")
 print("cohort=1296 queue=3888 pending/bootstrap/background/attempt0/unowned")
 print("foreign_background_jobs=0 physical_attempts_after_marker=0")
 print("collectors=hnl-01,kah-01,tcou identity/enabled/undrained/idle: PASS")
 print(f"aggregate_physical_attempt_ceiling={GLOBAL_ATTEMPT_CEILING} duration_hours=3")
 print("database writes: 0")
 print("Battlelog requests: 0")
 print("PHASE 5B STEP 7 LAUNCH PREFLIGHT: PASS")
 return 0
if __name__=="__main__": raise SystemExit(main())
