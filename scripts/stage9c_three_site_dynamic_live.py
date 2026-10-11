"""Bounded real three-site dynamic detailed queue trial on existing D2 cohort.

Refreshes the nine already-verified soldiers without node-specific partitions.
Each node claims up to three jobs from the SAME unrestricted cohort.
No retries, daemons, production writes or schema migrations.
"""
from __future__ import annotations
import argparse
import os
from sqlalchemy import text
from bf4ps.collection_jobs import enqueue_job
from bf4ps.detailed_collector import CollectorIdentity,CollectedJob,collect_one_detailed_job
from scripts.stage9c_three_site_live_ignition import engine,validate,NODES,UUIDS

BASELINE=86
CEILING=9
RUN="bf4ps-live-three-site-dynamic-20261011-v1"

def guard(conn):
    ids=validate(conn)
    if len(ids)!=9:
        raise RuntimeError("cohort mismatch")
    if conn.execute(text("SELECT count(*) FROM collection_events WHERE event_id>:baseline"),{"baseline":BASELINE}).scalar_one()<0:
        raise RuntimeError("invalid event count")
    return sorted(ids.values())

def prepare(e):
    if os.uname().nodename!="tcou":raise RuntimeError("prepare requires tcou")
    with e.begin() as conn:
        ids=guard(conn)
        if conn.execute(text("SELECT max(event_id) FROM collection_events")).scalar_one()!=BASELINE:
            raise RuntimeError("not at verified baseline")
        if conn.execute(text("SELECT count(*) FROM collection_jobs")).scalar_one():
            raise RuntimeError("queue not empty")
        for sid in ids:
            state=conn.execute(text("SELECT detailed_state FROM collection_state WHERE soldier_id=:sid"),{"sid":sid}).scalar_one()
            if state!="success":raise RuntimeError("not previously successful")
        for sid in ids:
            enqueue_job(conn,soldier_id=sid,resource="detailed",lane="background",priority_class="bootstrap",reason=RUN)
    print("DYNAMIC PREPARE PASS nine detailed refresh jobs, no partition, nine-attempt ceiling",flush=True)

def work(e,node):
    if os.uname().nodename!=node:raise RuntimeError("hostname mismatch")
    with e.connect() as conn:
        ids=guard(conn)
        if conn.execute(text("SELECT count(*) FROM collection_events WHERE event_id>:base AND collector_uuid=:uuid"),{"base":BASELINE,"uuid":UUIDS[node]}).scalar_one():
            raise RuntimeError("this worker has already run")
    identity=CollectorIdentity(collector_uuid=UUIDS[node],
        collector_name="bf4ps-live-three-site-ignition-20261011-v1:"+node,
        hostname=node,egress_key="bf4ps-live-three-site-ignition-20261011-v1:"+node,lane="background")
    for i in range(3):
        result=collect_one_detailed_job(e,identity=identity,
            request_interval_seconds=10.0,allowed_soldier_ids=ids,
            max_total_attempts=CEILING,attempts_after_event_id=BASELINE,
            attempt_ceiling_resources=["detailed"],enforce_production_budget=True,
            lease_seconds=120,timeout_seconds=30.0,retry_after_seconds=3600)
        print(f"DYNAMIC node={node} slot={i+1}/3 result={result!r}",flush=True)
        if not isinstance(result,CollectedJob):
            raise RuntimeError("not enough eligible jobs; stop, do not retry")
    print(f"DYNAMIC WORKER PASS {node}",flush=True)

def verify(e):
    with e.connect() as conn:
        ids=guard(conn)
        events=conn.execute(text("""SELECT soldier_id,event_type,collector_uuid
            FROM collection_events WHERE event_id>:baseline AND resource='detailed'
            ORDER BY event_id"""),{"baseline":BASELINE}).all()
        outstanding=conn.execute(text("SELECT count(*) FROM collection_jobs")).scalar_one()
        counts={node:0 for node in NODES}
        for sid in ids:
            own=[(typ,uuid) for soldier,typ,uuid in events if soldier==sid]
            if len(own)!=2 or [typ for typ,uuid in own]!=["collection_attempt_started","collection_success"] or own[0][1]!=own[1][1]:
                raise RuntimeError(f"incorrect event pair for soldier {sid}: {own}")
            node=next((n for n in NODES if UUIDS[n]==own[0][1]),None)
            if node is None:raise RuntimeError("unknown collector")
            counts[node]+=1
        print(f"DYNAMIC VERIFY counts={counts} events={len(events)} outstanding={outstanding}",flush=True)
        if len(events)!=18 or outstanding or any(n!=3 for n in counts.values()):
            raise RuntimeError("incomplete dynamic trial")
    print("THREE-SITE DYNAMIC LIVE PASS",flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("command",choices=("prepare","work","verify"))
    p.add_argument("--node",choices=NODES)
    p.add_argument("--execute",action="store_true")
    a=p.parse_args()
    if a.command!="verify" and not a.execute:p.error("--execute required")
    e=engine()
    if a.command=="prepare":prepare(e)
    elif a.command=="work":
        if not a.node:p.error("--node required")
        work(e,a.node)
    else:verify(e)
if __name__=="__main__":main()
