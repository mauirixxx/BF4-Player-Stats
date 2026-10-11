"""Live D2 post-HTTP abandoned-response and stale persistence fencing proof.

A Kahului worker claims a job, records physical request start, fetches a real
Battlelog response, and exits without persistence. After lease expiry,
Honolulu retries and commits. A stale attempt to persist the abandoned
response is rejected by the real persistence function.
"""
from __future__ import annotations
import argparse,os
from datetime import datetime,timezone
from sqlalchemy import text
from bf4ps.collection_jobs import ClaimedJob,enqueue_job,claim_next_job,mark_job_running
from bf4ps.detailed_collector import (
    CollectorIdentity,CollectedJob,collect_one_detailed_job,_record_detailed_attempt_started,
)
from bf4ps.battlelog_detailed import fetch_detailed_stats,normalize_detailed_stats
from bf4ps.detailed_persistence import persist_detailed_success,DETAILED_FIELDS
from bf4ps.request_gate import reserve_request_slot
from scripts.stage9c_three_site_live_ignition import engine,validate,UUIDS,RUN

BASELINE=106
VICTIM="kah-01"
RESCUER="hnl-01"
TAG="bf4ps-d2-post-http-abandoned-v1"

def ident(node):
    return CollectorIdentity(collector_uuid=UUIDS[node],collector_name=RUN+":"+node,
                             hostname=node,egress_key=RUN+":"+node,lane="background")

def guard(conn):
    ids=validate(conn)
    if len(ids)!=9:raise RuntimeError("cohort mismatch")
    return sorted(ids.values())

def prepare(e):
    if os.uname().nodename!="tcou":raise RuntimeError("wrong host")
    with e.begin() as c:
        ids=guard(c)
        if c.execute(text("SELECT COALESCE(MAX(event_id),0) FROM collection_events")).scalar_one()!=BASELINE:
            raise RuntimeError("baseline mismatch")
        if c.execute(text("SELECT count(*) FROM collection_jobs")).scalar_one():
            raise RuntimeError("queue not empty")
        jid=enqueue_job(c,soldier_id=ids[0],resource="detailed",lane="background",
                        priority_class="bootstrap",reason=TAG)
    print(f"PREPARE PASS job={jid} soldier={ids[0]}",flush=True)

def victim(e):
    if os.uname().nodename!=VICTIM:raise RuntimeError("wrong host")
    ci=ident(VICTIM)
    with e.begin() as c:
        ids=guard(c)
        job=claim_next_job(c,collector_uuid=ci.collector_uuid,resource="detailed",
                           lane="background",lease_seconds=12,allowed_soldier_ids=ids,
                           max_total_attempts=2,attempts_after_event_id=BASELINE,
                           attempt_ceiling_resources=["detailed"])
        if job is None or not mark_job_running(c,job):raise RuntimeError("claim failed")
    with e.connect() as c:
        persona,platform=c.execute(text("SELECT persona_id,platform FROM soldiers WHERE soldier_id=:sid"),{"sid":job.soldier_id}).one()
    with e.begin() as c:
        permit=reserve_request_slot(c,egress_key=ci.egress_key,interval_seconds=10.0)
    if permit.wait_seconds>0:
        from time import sleep
        sleep(permit.wait_seconds)
    _record_detailed_attempt_started(e,job=job,identity=ci,persona_id=persona,platform=platform)
    fetched=fetch_detailed_stats(persona,platform,timeout_seconds=30.0)
    stats=normalize_detailed_stats(fetched.payload,expected_persona_id=persona,
                                   expected_platform_int=fetched.platform_int)
    if not stats:raise RuntimeError("empty normalized payload")
    print(f"VICTIM FETCH PASS job={job.job_id} attempt=1 fields={len(stats)}; intentionally abandoning response before persistence",flush=True)

def rescue(e):
    if os.uname().nodename!=RESCUER:raise RuntimeError("wrong host")
    with e.connect() as c:
        ids=guard(c)
        row=c.execute(text("SELECT status,collector_uuid,attempt_count,lease_expires_at<=now() AS expired FROM collection_jobs")).one()
        ev=c.execute(text("SELECT event_type,collector_uuid,attempt_number FROM collection_events WHERE event_id>:base ORDER BY event_id"),{"base":BASELINE}).all()
        if row is None or row.status!="running" or row.collector_uuid!=UUIDS[VICTIM] or row.attempt_count!=1 or not row.expired:
            raise RuntimeError(f"victim lease not expired: {row}")
        if len(ev)!=1 or ev[0].event_type!="collection_attempt_started" or ev[0].collector_uuid!=UUIDS[VICTIM] or ev[0].attempt_number!=1:
            raise RuntimeError(f"unexpected victim event ledger {ev}")
    result=collect_one_detailed_job(e,identity=ident(RESCUER),request_interval_seconds=10,
        lease_seconds=120,timeout_seconds=30,retry_after_seconds=3600,
        allowed_soldier_ids=ids,max_total_attempts=2,attempts_after_event_id=BASELINE,
        attempt_ceiling_resources=["detailed"],enforce_production_budget=True)
    if not isinstance(result,CollectedJob):raise RuntimeError(f"rescue failed {result!r}")
    print(f"RESCUE PASS {result!r}",flush=True)

def stale(e):
    if os.uname().nodename!="tcou":raise RuntimeError("wrong host")
    with e.begin() as c:
        ids=guard(c)
        row=c.execute(text("""SELECT job_id,soldier_id,attempt_number,lease_token,persona_id,platform
            FROM collection_events WHERE event_id>:base AND event_type='collection_attempt_started'
            AND collector_uuid=:uuid"""),{"base":BASELINE,"uuid":UUIDS[VICTIM]}).one()
        if row is None:raise RuntimeError("missing original attempt event")
        stats=c.execute(text("SELECT "+",".join(DETAILED_FIELDS)+" FROM detailed_stats_current WHERE soldier_id=:sid"),{"sid":row.soldier_id}).mappings().one()
        old=ClaimedJob(job_id=row.job_id,soldier_id=row.soldier_id,resource="detailed",
            lane="background",attempt_count=row.attempt_number,
            collector_uuid=UUIDS[VICTIM],lease_token=row.lease_token)
        try:
            persist_detailed_success(c,job=old,stats=dict(stats),
                source_fetched_at=datetime.now(timezone.utc),persona_id=row.persona_id,
                platform=row.platform,collector_name=RUN+":"+VICTIM,hostname=VICTIM,
                egress_key=RUN+":"+VICTIM,duration_ms=1,http_status=200)
        except RuntimeError as exc:
            if str(exc)!="detailed success rejected: job lease is no longer owned":
                raise
        else:
            raise RuntimeError("stale persistence accepted")
    print("STALE PERSISTENCE REJECTED PASS",flush=True)

def verify(e):
    with e.connect() as c:
        ids=guard(c)
        events=c.execute(text("""SELECT event_type,collector_uuid,attempt_number
            FROM collection_events WHERE event_id>:base ORDER BY event_id"""),{"base":BASELINE}).all()
        jobs=c.execute(text("SELECT count(*) FROM collection_jobs")).scalar_one()
        print(f"VERIFY events={events} jobs={jobs}",flush=True)
        if len(events)!=3 or [x.event_type for x in events]!=["collection_attempt_started","collection_attempt_started","collection_success"]:
            raise RuntimeError("event sequence mismatch")
        if [(x.collector_uuid,x.attempt_number) for x in events]!=[
            (UUIDS[VICTIM],1),(UUIDS[RESCUER],2),(UUIDS[RESCUER],2)] or jobs:
            raise RuntimeError("ownership/queue mismatch")
    print("POST-HTTP ABANDONMENT LIVE PASS",flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("command",choices=("prepare","victim","rescue","stale","verify"))
    p.add_argument("--execute",action="store_true")
    a=p.parse_args()
    if a.command!="verify" and not a.execute:p.error("--execute required")
    {"prepare":prepare,"victim":victim,"rescue":rescue,"stale":stale,"verify":verify}[a.command](engine())
if __name__=="__main__":main()
