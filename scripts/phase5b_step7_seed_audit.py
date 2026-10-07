#!/usr/bin/env python3
"""Read-only audit of the seeded Phase 5B Step 7 queue."""
from __future__ import annotations
import os
from urllib.parse import urlsplit
from sqlalchemy import create_engine,text
from bf4ps.phase5b_step7_endurance import (
 EXPECTED_DATABASE,EXPECTED_REVISION,INITIAL_JOB_COUNT,JOB_REASON,PLATFORMS,
 PRIORITY_CLASS,RESOURCES,RUN_MARKER_EVENT_TYPE,RUN_NUMBER,SOLDIERS_PER_PLATFORM,
)
def main()->int:
 url=os.environ.get("BF4PS_DATABASE_URL"); parsed=urlsplit(url or "")
 if not url or parsed.path.lstrip("/")!=EXPECTED_DATABASE: raise SystemExit("REFUSING: wrong or missing BF4PS_DATABASE_URL")
 engine=create_engine(url,pool_pre_ping=True)
 with engine.connect() as conn:
  if conn.execute(text("SELECT current_database()")).scalar_one()!=EXPECTED_DATABASE: raise RuntimeError("wrong database")
  if conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()!=EXPECTED_REVISION: raise RuntimeError("wrong revision")
  rows=conn.execute(text("""
   SELECT event_id,metadata FROM collection_events
   WHERE event_type=:t AND metadata->>'run_number'=:n ORDER BY event_id
  """),{"t":RUN_MARKER_EVENT_TYPE,"n":str(RUN_NUMBER)}).mappings().all()
  if len(rows)!=1: raise RuntimeError(f"expected one marker; found {len(rows)}")
  marker=int(rows[0]["event_id"]); meta=rows[0]["metadata"]; ids=[int(x) for x in meta["cohort_soldier_ids"]]
  if len(ids)!=1296 or len(set(ids))!=1296: raise RuntimeError("marker cohort invalid")
  platform_counts=dict(conn.execute(text(
   "SELECT platform,COUNT(*) FROM soldiers WHERE soldier_id=ANY(:ids) GROUP BY platform"
  ),{"ids":ids}).all())
  if platform_counts!={p:SOLDIERS_PER_PLATFORM for p in PLATFORMS}: raise RuntimeError(f"platform imbalance: {platform_counts}")
  shape=conn.execute(text("""
   SELECT COUNT(*) total,COUNT(DISTINCT (soldier_id,resource)) pairs,
    COUNT(*) FILTER (WHERE lane='background' AND priority_class=:pc AND reason=:reason
      AND status='pending' AND attempt_count=0 AND collector_uuid IS NULL
      AND lease_token IS NULL AND claimed_at IS NULL AND started_at IS NULL
      AND lease_expires_at IS NULL) good
   FROM collection_jobs WHERE soldier_id=ANY(:ids) AND resource=ANY(:resources)
  """),{"ids":ids,"resources":list(RESOURCES),"pc":PRIORITY_CLASS,"reason":JOB_REASON}).mappings().one()
  attempts=int(conn.execute(text("""
   SELECT COUNT(*) FROM collection_events WHERE event_id>:marker AND soldier_id=ANY(:ids)
    AND resource=ANY(:resources) AND event_type='collection_attempt_started'
  """),{"marker":marker,"ids":ids,"resources":list(RESOURCES)}).scalar_one())
  bg=int(conn.execute(text("""
   SELECT COUNT(*) FROM collection_jobs WHERE lane='background'
    AND NOT (soldier_id=ANY(:ids) AND resource=ANY(:resources))
  """),{"ids":ids,"resources":list(RESOURCES)}).scalar_one())
  if int(shape["total"])!=INITIAL_JOB_COUNT or int(shape["pairs"])!=INITIAL_JOB_COUNT or int(shape["good"])!=INITIAL_JOB_COUNT:
   raise RuntimeError(f"queue shape mismatch: {dict(shape)}")
  if attempts: raise RuntimeError(f"physical attempts already exist: {attempts}")
  if bg: raise RuntimeError(f"foreign background jobs exist: {bg}")
 engine.dispose()
 print("===== BF4PS PHASE 5B STEP 7 SEEDED-QUEUE AUDIT =====")
 print(f"run_marker_event_id={marker}")
 print(f"cohort=1296 platforms=432pc/432ps4/432xboxone")
 print(f"queue_jobs={INITIAL_JOB_COUNT} unique_soldier_resource_pairs={INITIAL_JOB_COUNT}")
 print("queue_shape=background/bootstrap/pending/attempt0/unowned")
 print("foreign_background_jobs=0")
 print("physical_attempts_after_marker=0")
 print("database writes: 0")
 print("Battlelog requests: 0")
 print("PHASE 5B STEP 7 SEEDED-QUEUE AUDIT: PASS")
 return 0
if __name__=="__main__": raise SystemExit(main())
