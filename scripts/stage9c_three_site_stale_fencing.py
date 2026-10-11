"""Isolated D2 stale-lease fencing integration proof.

No HTTP. Kahului claims a job, Honolulu reclaims it after lease expiry,
and tcou verifies stale-token mutations are rejected before the replacement
owner finalizes the job. Production is never used.
"""
from __future__ import annotations
import argparse
import os
from sqlalchemy import text
from bf4ps.collection_jobs import (
    enqueue_job,claim_next_job,mark_job_running,renew_lease,
    release_for_retry,finalize_owned_job,ClaimedJob,
)
from scripts.stage9c_three_site_live_ignition import engine,validate,UUIDS

BASELINE=106
SOURCE="bf4ps-stale-fencing-integration-v1"
VICTIM="kah-01"
RESCUER="hnl-01"
def guard(conn):
    ids=validate(conn)
    return sorted(ids.values())
def prepare(e):
    if os.uname().nodename!="tcou":raise RuntimeError("prepare must run on tcou")
    with e.begin() as conn:
        ids=guard(conn)
        if conn.execute(text("SELECT COALESCE(MAX(event_id),0) FROM collection_events")).scalar_one()!=BASELINE:
            raise RuntimeError("unexpected event baseline")
        if conn.execute(text("SELECT count(*) FROM collection_jobs")).scalar_one():
            raise RuntimeError("nonempty queue")
        sid=ids[0]
        jid=enqueue_job(conn,soldier_id=sid,resource="detailed",
                        lane="background",priority_class="bootstrap",reason=SOURCE)
    print(f"PREPARE PASS job={jid} soldier={sid}",flush=True)
def claim(e):
    if os.uname().nodename!=VICTIM:raise RuntimeError("victim hostname mismatch")
    with e.begin() as conn:
        ids=guard(conn)
        job=claim_next_job(conn,collector_uuid=UUIDS[VICTIM],
                           lane="background",resource="detailed",
                           lease_seconds=8,allowed_soldier_ids=ids,
                           max_total_attempts=2,attempts_after_event_id=BASELINE,
                           attempt_ceiling_resources=["detailed"])
        if job is None or not mark_job_running(conn,job):
            raise RuntimeError("failed victim claim")
    print(f"VICTIM PASS job={job.job_id} attempt={job.attempt_count}",flush=True)
def takeover(e):
    if os.uname().nodename!=RESCUER:raise RuntimeError("rescue hostname mismatch")
    with e.begin() as conn:
        ids=guard(conn)
        row=conn.execute(text("SELECT job_id,status,collector_uuid,attempt_count,lease_expires_at<=now() AS expired FROM collection_jobs")).one()
        if row is None or row.status!="running" or row.collector_uuid!=UUIDS[VICTIM] or row.attempt_count!=1 or not row.expired:
            raise RuntimeError(f"victim lease not expired: {row}")
        job=claim_next_job(conn,collector_uuid=UUIDS[RESCUER],lane="background",
                           resource="detailed",lease_seconds=120,
                           allowed_soldier_ids=ids,max_total_attempts=2,
                           attempts_after_event_id=BASELINE,attempt_ceiling_resources=["detailed"])
        if job is None or job.attempt_count!=2 or not mark_job_running(conn,job):
            raise RuntimeError("takeover failed")
    print(f"TAKEOVER PASS job={job.job_id} attempt={job.attempt_count}",flush=True)
def fence(e):
    if os.uname().nodename!="tcou":raise RuntimeError("fence requires tcou")
    with e.begin() as conn:
        ids=guard(conn)
        row=conn.execute(text("""SELECT job_id,soldier_id,resource,lane,attempt_count,
            collector_uuid,lease_token FROM collection_jobs""")).one()
        if row is None or row.collector_uuid!=UUIDS[RESCUER] or row.attempt_count!=2:
            raise RuntimeError("replacement owner missing")
        # Simulate the original worker waking with its old collector UUID and
        # an obsolete token. Any token other than the current token is stale.
        from uuid import uuid4
        stale=ClaimedJob(job_id=row.job_id,soldier_id=row.soldier_id,
            resource=row.resource,lane=row.lane,attempt_count=1,
            collector_uuid=UUIDS[VICTIM],lease_token=uuid4())
        checks={
            "renew":renew_lease(conn,stale,lease_seconds=120),
            "release":release_for_retry(conn,stale,retry_after_seconds=3600),
            "finalize":finalize_owned_job(conn,stale),
            "mark_running":mark_job_running(conn,stale),
        }
        if any(checks.values()):raise RuntimeError(f"STALE MUTATION ACCEPTED {checks}")
        current=conn.execute(text("""SELECT job_id,status,collector_uuid,lease_token,
            attempt_count FROM collection_jobs""")).one()
        if current is None or current.status!="running" or current.collector_uuid!=UUIDS[RESCUER] or current.lease_token!=row.lease_token or current.attempt_count!=2:
            raise RuntimeError("replacement job changed by stale owner")
        print(f"FENCING PASS stale rejected={checks}",flush=True)
def finish(e):
    if os.uname().nodename!=RESCUER:raise RuntimeError("finish hostname mismatch")
    with e.begin() as conn:
        guard(conn)
        row=conn.execute(text("""SELECT job_id,soldier_id,resource,lane,attempt_count,
            collector_uuid,lease_token FROM collection_jobs""")).one()
        if row is None or row.collector_uuid!=UUIDS[RESCUER] or row.attempt_count!=2:
            raise RuntimeError("replacement owner missing")
        job=ClaimedJob(job_id=row.job_id,soldier_id=row.soldier_id,resource=row.resource,
            lane=row.lane,attempt_count=row.attempt_count,collector_uuid=row.collector_uuid,
            lease_token=row.lease_token)
        if not finalize_owned_job(conn,job):
            raise RuntimeError("replacement finalize failed")
    print("REPLACEMENT FINALIZATION PASS (no HTTP by design)",flush=True)
def verify(e):
    with e.connect() as conn:
        guard(conn)
        jobs=conn.execute(text("SELECT count(*) FROM collection_jobs")).scalar_one()
        events=conn.execute(text("SELECT count(*) FROM collection_events WHERE event_id>:baseline"),{"baseline":BASELINE}).scalar_one()
        if jobs or events:raise RuntimeError(f"unexpected jobs/events: {jobs}/{events}")
    print("STALE FENCING INTEGRATION PASS",flush=True)
def main():
    p=argparse.ArgumentParser()
    p.add_argument("command",choices=("prepare","claim","takeover","fence","finish","verify"))
    p.add_argument("--execute",action="store_true")
    a=p.parse_args()
    if a.command!="verify" and not a.execute:p.error("--execute required")
    {"prepare":prepare,"claim":claim,"takeover":takeover,"fence":fence,"finish":finish,"verify":verify}[a.command](engine())
if __name__=="__main__":main()
