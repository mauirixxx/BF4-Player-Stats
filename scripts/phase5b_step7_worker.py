#!/usr/bin/env python3
"""Phase 5B Step 7 time- and attempt-bounded distributed endurance worker."""
from __future__ import annotations
import os,signal,socket,time
from datetime import timedelta
from urllib.parse import urlsplit
from sqlalchemy import create_engine,text
from bf4ps.collector_runtime import heartbeat_collector,register_collector,stop_collector
from bf4ps.detailed_collector import CollectorIdentity,CollectedJob,FailedJob,collect_one_detailed_job
from bf4ps.weapon_collector import CollectedWeaponJob,FailedWeaponJob,collect_one_weapon_job
from bf4ps.vehicle_collector import CollectedVehicleJob,FailedVehicleJob,collect_one_vehicle_job
from bf4ps.phase5b_step7_endurance import (
 DURATION,EXPECTED_DATABASE,EXPECTED_REVISION,FROZEN_UUIDS,GLOBAL_ATTEMPT_CEILING,
 HOSTS,LEASE_SECONDS,REQUEST_INTERVAL_SECONDS,RESOURCES,RUN_MARKER_EVENT_TYPE,
 RUN_NUMBER,SOFTWARE_VERSION,
)
STOP=False
def request_stop(*_):
 global STOP; STOP=True
def _target(conn):
 db=conn.execute(text("SELECT current_database()")).scalar_one()
 rev=conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
 rec=bool(conn.execute(text("SELECT pg_is_in_recovery()")).scalar_one()
 )
 ro=conn.execute(text("SELECT current_setting('transaction_read_only')")).scalar_one()
 if db!=EXPECTED_DATABASE or rev!=EXPECTED_REVISION or rec or ro!="off":
  raise RuntimeError(f"wrong target db={db!r} revision={rev!r} recovery={rec} read_only={ro!r}")
def _run(conn):
 rows=conn.execute(text("""
  SELECT event_id,occurred_at,metadata FROM collection_events
  WHERE event_type=:t AND metadata->>'run_number'=:n ORDER BY event_id
 """),{"t":RUN_MARKER_EVENT_TYPE,"n":str(RUN_NUMBER)}).mappings().all()
 if len(rows)!=1: raise RuntimeError(f"expected one Step 7 marker; found {len(rows)}")
 meta=rows[0]["metadata"]; ids=tuple(int(x) for x in meta["cohort_soldier_ids"])
 if len(ids)!=1296 or len(set(ids))!=1296: raise RuntimeError("invalid frozen Step 7 allowlist")
 if int(meta["global_attempt_ceiling"])!=GLOBAL_ATTEMPT_CEILING: raise RuntimeError("marker ceiling mismatch")
 return int(rows[0]["event_id"]),rows[0]["occurred_at"],ids
def _attempts(conn,boundary,ids):
 return int(conn.execute(text("""
  SELECT COUNT(*) FROM (
   SELECT job_id,attempt_number FROM collection_events
   WHERE event_id>:b AND soldier_id=ANY(:ids) AND resource=ANY(:resources)
    AND lane='background' AND event_type='collection_attempt_started'
   GROUP BY job_id,attempt_number
  ) q
 """),{"b":boundary,"ids":list(ids),"resources":list(RESOURCES)}).scalar_one())
def safety(conn,boundary,ids):
 _target(conn)
 foreign=int(conn.execute(text("""
  SELECT COUNT(*) FROM collection_jobs WHERE lane='background'
   AND NOT (soldier_id=ANY(:ids) AND resource=ANY(:resources))
 """),{"ids":list(ids),"resources":list(RESOURCES)}).scalar_one())
 bad_owner=int(conn.execute(text("""
  SELECT COUNT(*) FROM collection_jobs WHERE soldier_id=ANY(:ids) AND resource=ANY(:resources)
   AND lane='background' AND status IN ('claimed','running')
   AND collector_uuid<>ALL(:uuids)
 """),{"ids":list(ids),"resources":list(RESOURCES),"uuids":list(FROZEN_UUIDS)}).scalar_one())
 attempts=_attempts(conn,boundary,ids)
 bad=int(conn.execute(text("""
  SELECT COUNT(*) FROM collection_events WHERE event_id>:b AND soldier_id=ANY(:ids)
   AND resource=ANY(:resources) AND
   (event_type='collection_persistence_failure' OR http_status IN (403,429)
    OR error_class='battlelog_throttle')
 """),{"b":boundary,"ids":list(ids),"resources":list(RESOURCES)}).scalar_one())
 if foreign or bad_owner or attempts>GLOBAL_ATTEMPT_CEILING or bad:
  raise RuntimeError(f"Step 7 safety failed foreign={foreign} bad_owner={bad_owner} attempts={attempts} abort_events={bad}")
 return attempts
def _collect(engine,identity,resource,boundary,ids):
 common=dict(identity=identity,request_interval_seconds=REQUEST_INTERVAL_SECONDS,
  lease_seconds=LEASE_SECONDS,allowed_soldier_ids=ids,max_total_attempts=GLOBAL_ATTEMPT_CEILING,
  attempts_after_event_id=boundary,attempt_ceiling_resources=RESOURCES,enforce_production_budget=True)
 if resource=="detailed": return collect_one_detailed_job(engine,timeout_seconds=30.0,**common)
 if resource=="weapons": return collect_one_weapon_job(engine,timeout_seconds=30.0,**common)
 if resource=="vehicles": return collect_one_vehicle_job(engine,timeout_seconds=30.0,**common)
 raise RuntimeError(resource)
def _print(n,r,o):
 if isinstance(o,(CollectedJob,CollectedWeaponJob,CollectedVehicleJob)):
  extra=""
  if isinstance(o,CollectedWeaponJob): extra=f" rows={o.weapon_rows} bytes={o.response_bytes}"
  if isinstance(o,CollectedVehicleJob): extra=f" rows={o.vehicle_rows} bytes={o.response_bytes}"
  print(f"[{n:04d}] SUCCESS resource={r} soldier={o.soldier_id} job={o.job_id} platform={o.platform}{extra} duration_ms={o.duration_ms}",flush=True); return False
 if isinstance(o,(FailedJob,FailedWeaponJob,FailedVehicleJob)):
  print(f"[{n:04d}] FAILURE resource={r} soldier={o.soldier_id} job={o.job_id} platform={o.platform} http={o.http_status} class={o.error_class} retry_after={o.retry_after_seconds}s duration_ms={o.duration_ms}",flush=True)
  return o.http_status in {403,429} or o.error_class=="battlelog_throttle"
 raise RuntimeError(type(o))
def main():
 host=socket.gethostname().split(".",1)[0]; frozen=HOSTS.get(host)
 if frozen is None: raise SystemExit(f"REFUSING: host {host!r} is not a frozen Step 7 collector")
 url=os.environ.get("BF4PS_DATABASE_URL"); parsed=urlsplit(url or "")
 if not url or parsed.path.lstrip("/")!=EXPECTED_DATABASE: raise SystemExit("REFUSING: wrong or missing BF4PS_DATABASE_URL")
 identity=CollectorIdentity(frozen.collector_uuid,frozen.collector_name,host,frozen.egress_key,"background")
 engine=create_engine(url,pool_pre_ping=True)
 with engine.begin() as conn:
  boundary,marker_at,ids=_run(conn); attempts=safety(conn,boundary,ids)
  # Duration begins when the first Step 7 worker registers, not when the queue was seeded.
  started=conn.execute(text("""
   SELECT MIN(started_at) FROM collectors WHERE collector_uuid=ANY(:uuids)
    AND software_version=:version AND started_at>:marker_at
  """),{"uuids":list(FROZEN_UUIDS),"version":SOFTWARE_VERSION,"marker_at":marker_at}).scalar_one()
  control=register_collector(conn,identity=identity,software_version=SOFTWARE_VERSION)
  if started is None: started=control.started_at
 deadline=started+DURATION
 print("===== BF4PS PHASE 5B STEP 7 ENDURANCE WORKER =====",flush=True)
 print(f"host={host} collector={frozen.collector_name} egress={frozen.egress_key}\nrun_marker_event_id={boundary} soldiers={len(ids)} resources={','.join(RESOURCES)}\nglobal_attempt_ceiling={GLOBAL_ATTEMPT_CEILING} duration_hours=3 request_spacing={REQUEST_INTERVAL_SECONDS:.1f}s production_budget=enabled\nrun_started_at={started.isoformat()} deadline={deadline.isoformat()} initial_attempts={attempts} drained={control.drained}",flush=True)
 signal.signal(signal.SIGTERM,request_stop); signal.signal(signal.SIGINT,request_stop)
 local=0; ri=0
 try:
  while not STOP:
   with engine.begin() as conn:
    now=conn.execute(text("SELECT now()")).scalar_one()
    attempts=safety(conn,boundary,ids)
    control=heartbeat_collector(conn,collector_uuid=frozen.collector_uuid,software_version=SOFTWARE_VERSION)
   if now>=deadline: print("3-hour endurance deadline reached",flush=True); break
   if attempts>=GLOBAL_ATTEMPT_CEILING: print("global 3888-attempt ceiling reached",flush=True); break
   if not control.enabled: print("collector disabled; clean stop",flush=True); break
   if control.drained: time.sleep(.5); continue
   r=RESOURCES[ri]; ri=(ri+1)%len(RESOURCES); o=_collect(engine,identity,r,boundary,ids)
   if o is None:
    # Budget saturation or temporary lack of work is expected; do not exit early.
    time.sleep(.5); continue
   local+=1
   if _print(local,r,o): print("THROTTLE SIGNAL; stopping",flush=True); break
 finally:
  with engine.begin() as conn: stop_collector(conn,collector_uuid=frozen.collector_uuid)
  engine.dispose()
 print(f"PHASE 5B STEP 7 WORKER STOPPED CLEANLY host={host} local_attempts={local}",flush=True)
 return 0
if __name__=="__main__": raise SystemExit(main())
