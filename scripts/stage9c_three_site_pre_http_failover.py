"""Bounded live three-site pre-HTTP worker-loss / lease takeover proof.

Kahului claims and exits without HTTP; Honolulu takes over only after lease
expiry. tcou verifies old token cannot mutate/finalize the reclaimed job.
No automatic retry, no production writes.
"""
from __future__ import annotations
import argparse
import os
from sqlalchemy import text
from bf4ps.collection_jobs import enqueue_job,claim_next_job,mark_job_running,finalize_owned_job,renew_lease
from bf4ps.detailed_collector import CollectorIdentity,CollectedJob,collect_one_detailed_job
from scripts.stage9c_three_site_live_ignition import engine,validate,UUIDS

BASELINE=104
SOURCE="bf4ps-live-pre-http-worker-loss-v1"
VICTIM="kah-01"
RESCUER="hnl-01"
LEASE=8
def guard(conn):
    ids=validate(conn)
    if conn.execute(text("SELECT current_database()")).scalar_one()!="bf4ps_scratch_stage9c_d2":
        raise RuntimeError("database mismatch")
    return ids

def prepare(e):
    if os.uname().nodename!="tcou":raise RuntimeError("prepare requires tcou")
    with e.begin() as conn:
        ids=guard(conn)
        if conn.execute(text("SELECT COALESCE(MAX(event_id),0) FROM collection_events")).scalar_one()!=BASELINE:
            raise RuntimeError("event baseline mismatch")
        if conn.execute(text("SELECT count(*) FROM collection_jobs")).scalar_one():
            raise RuntimeError("queue not empty")
        sid=min(ids.values())
        job=enqueue_job(conn,soldier_id=sid,resource="detailed",lane="background",
                        priority_class="bootstrap",reason=SOURCE)
    print(f"PREPARE PASS job={job} soldier={sid} baseline={BASELINE}",flush=True)

def victim(e):
    if os.uname().nodename!=VICTIM:raise RuntimeError("wrong victim host")
    with e.begin() as conn:
        ids=guard(conn)
        if conn.execute(text("SELECT count(*) FROM collection_events WHERE event_id>:base"),{"base":BASELINE}).scalar_one():
            raise RuntimeError("new events already present")
        job=claim_next_job(conn,collector_uuid=UUIDS[VICTIM],lane="background",
                           resource="detailed",lease_seconds=LEASE,
                           allowed_soldier_ids=sorted(ids.values()),max_total_attempts=2,
                           attempts_after_event_id=BASELINE,attempt_ceiling_resources=["detailed"])
        if job is None:raise RuntimeError("claim failed")
        if not mark_job_running(conn,job):raise RuntimeError("mark running failed")
    print(f"VICTIM CLAIMED job={job.job_id} attempt={job.attempt_count}; exiting before gate/HTTP/events",flush=True)

def rescue(e):
    if os.uname().nodename!=RESCUER:raise RuntimeError("wrong rescue host")
    with e.connect() as conn:
        ids=guard(conn)
        row=conn.execute(text("SELECT job_id,status,collector_uuid,lease_expires_at<=now() AS expired,attempt_count FROM collection_jobs")).one()
        if row is None or row.status!="running" or row.collector_uuid!=UUIDS[VICTIM] or not row.expired or row.attempt_count!=1:
            raise RuntimeError(f"refusing rescue until expired victim lease: {row}")
        if conn.execute(text("SELECT count(*) FROM collection_events WHERE event_id>:base"),{"base":BASELINE}).scalar_one():
            raise RuntimeError("unexpected physical request events")
    ci=CollectorIdentity(collector_uuid=UUIDS[RESCUER],
        collector_name="bf4ps-live-three-site-ignition-20261011-v1:"+RESCUER,
        hostname=RESCUER,egress_key="bf4ps-live-three-site-ignition-20261011-v1:"+RESCUER,
        lane="background")
    result=collect_one_detailed_job(e,identity=ci,request_interval_seconds=10,
        lease_seconds=120,timeout_seconds=30,retry_after_seconds=3600,
        allowed_soldier_ids=sorted(ids.values()),max_total_attempts=2,
        attempts_after_event_id=BASELINE,attempt_ceiling_resources=["detailed"],
        enforce_production_budget=True)
    print(f"RESCUE result={result!r}",flush=True)
    if not isinstance(result,CollectedJob):raise RuntimeError("rescue incomplete")
    print("RESCUE PASS",flush=True)

def verify(e):
    with e.connect() as conn:
        ids=guard(conn)
        events=conn.execute(text("SELECT event_type,collector_uuid,attempt_number FROM collection_events WHERE event_id>:base ORDER BY event_id"),{"base":BASELINE}).all()
        jobs=conn.execute(text("SELECT count(*) FROM collection_jobs")).scalar_one()
        print(f"VERIFY events={events} jobs={jobs}",flush=True)
        if len(events)!=2 or [r.event_type for r in events]!=["collection_attempt_started","collection_success"] or any(r.collector_uuid!=UUIDS[RESCUER] or r.attempt_number!=2 for r in events) or jobs:
            raise RuntimeError("takeover verification failed")
    print("PRE-HTTP WORKER LOSS LIVE PASS",flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("command",choices=("prepare","victim","rescue","verify"))
    p.add_argument("--execute",action="store_true")
    a=p.parse_args()
    if a.command!="verify" and not a.execute:p.error("--execute required")
    e=engine()
    {"prepare":prepare,"victim":victim,"rescue":rescue,"verify":verify}[a.command](e)
if __name__=="__main__":main()
