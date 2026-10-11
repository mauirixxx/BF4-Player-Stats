"""Three-site live weapons+vehicles follow-up to the successful D2 detailed ignition.

Requires the exact nine-soldier pristine post-ignition D2 cohort.
All nodes share the original collectors and a durable event baseline.
Explicit --execute required. No automatic retry or production changes.
"""
from __future__ import annotations
import argparse
import os
from sqlalchemy import text
from bf4ps.collection_jobs import enqueue_job
from bf4ps.weapon_collector import CollectorIdentity as WeaponIdentity,CollectedWeaponJob,collect_one_weapon_job
from bf4ps.vehicle_collector import CollectorIdentity as VehicleIdentity,CollectedVehicleJob,collect_one_vehicle_job
from scripts.stage9c_three_site_live_ignition import engine,validate,COHORT,NODES,UUIDS
RESOURCES=("weapons","vehicles")
BASELINE=50
MAX_ATTEMPTS=18
TABLES={"weapons":"soldier_weapon_stats","vehicles":"soldier_vehicle_stats"}

def preflight(conn):
    ids=validate(conn)
    events=conn.execute(text("SELECT event_id,event_type,resource FROM collection_events WHERE event_id<=:baseline ORDER BY event_id"),{"baseline":BASELINE}).all()
    if len(events)!=18 or any(resource!="detailed" or typ not in ("collection_attempt_started","collection_success") for _,typ,resource in events):
        raise RuntimeError("unexpected detailed ignition events")
    if events[-1][0]!=BASELINE:
        raise RuntimeError("unexpected baseline event ID; inspect D2 before proceeding")
    return ids

def prepare(e):
    if os.uname().nodename!="tcou":
        raise RuntimeError("prepare only from tcou")
    with e.begin() as conn:
        ids=preflight(conn)
        if conn.execute(text("SELECT count(*) FROM collection_jobs")).scalar_one():
            raise RuntimeError("queue not empty")
        for sid in ids.values():
            for resource in RESOURCES:
                state=conn.execute(text("SELECT "+resource+"_state FROM collection_state WHERE soldier_id=:sid"),{"sid":sid}).scalar_one()
                if state!="never_attempted":
                    raise RuntimeError("resource already attempted")
        for sid in ids.values():
            for resource in RESOURCES:
                enqueue_job(conn,soldier_id=sid,resource=resource,lane="background",
                            priority_class="bootstrap",reason="three_site_live_multiresource_v1")
    print("PREPARE PASS nine soldiers, 18 jobs, 18 global attempts, baseline 50",flush=True)

def work(e,node):
    if os.uname().nodename!=node:
        raise RuntimeError("worker hostname mismatch")
    with e.connect() as conn:
        ids=preflight(conn)
        own=[ids[persona] for name,persona,owner in COHORT if owner==node]
        for resource in RESOURCES:
            pending=conn.execute(text("SELECT soldier_id,status FROM collection_jobs WHERE resource=:resource"),{"resource":resource}).all()
            if any(sid not in ids.values() or status not in ("pending","claimed","running") for sid,status in pending):
                raise RuntimeError("foreign or unexpected job")
            own_pending=[(sid,status) for sid,status in pending if sid in own]
            if len(own_pending)!=3 or any(status!="pending" for _,status in own_pending):
                raise RuntimeError("own resource partition already started")
        prior=conn.execute(text("SELECT count(*) FROM collection_events WHERE event_id>:baseline AND soldier_id=ANY(:ids)"),{"baseline":BASELINE,"ids":own}).scalar_one()
        if prior:
            raise RuntimeError("own partition already has attempts")
    for resource,identity_cls,success_cls,collector in (
        ("weapons",WeaponIdentity,CollectedWeaponJob,collect_one_weapon_job),
        ("vehicles",VehicleIdentity,CollectedVehicleJob,collect_one_vehicle_job)):
        ci=identity_cls(collector_uuid=UUIDS[node],collector_name="bf4ps-live-three-site-ignition-20261011-v1:"+node,
                        hostname=node,egress_key="bf4ps-live-three-site-ignition-20261011-v1:"+node,lane="background")
        for i in range(3):
            result=collector(e,identity=ci,request_interval_seconds=10.0,
                allowed_soldier_ids=own,max_total_attempts=MAX_ATTEMPTS,
                attempts_after_event_id=BASELINE,attempt_ceiling_resources=list(RESOURCES),
                enforce_production_budget=True,lease_seconds=120,
                timeout_seconds=30.0,retry_after_seconds=3600)
            print(f"COLLECT node={node} resource={resource} {i+1}/3 {result!r}",flush=True)
            if not isinstance(result,success_cls):
                raise RuntimeError("collection incomplete; stop without retry")
    print(f"WORKER PASS node={node} resources=weapons,vehicles",flush=True)

def verify(e):
    with e.connect() as conn:
        ids=preflight(conn)
        events=conn.execute(text("""SELECT soldier_id,resource,event_type,collector_uuid
            FROM collection_events WHERE event_id>:baseline ORDER BY event_id"""),{"baseline":BASELINE}).all()
        print(f"VERIFY new_events={len(events)} jobs={conn.execute(text('SELECT count(*) FROM collection_jobs')).scalar_one()}",flush=True)
        for name,persona,node in COHORT:
            sid=ids[persona]
            for resource in RESOURCES:
                state=conn.execute(text("SELECT "+resource+"_state FROM collection_state WHERE soldier_id=:sid"),{"sid":sid}).scalar_one()
                count=conn.execute(text("SELECT count(*) FROM "+TABLES[resource]+" WHERE soldier_id=:sid"),{"sid":sid}).scalar_one()
                ev=[typ for soldier,res,typ,uuid in events if soldier==sid and res==resource]
                owned=all(uuid==UUIDS[node] for soldier,res,typ,uuid in events if soldier==sid and res==resource)
                jobs=conn.execute(text("SELECT count(*) FROM collection_jobs WHERE soldier_id=:sid AND resource=:res"),{"sid":sid,"res":resource}).scalar_one()
                print(f"RESULT node={node} name={name} resource={resource} rows={count} state={state} events={ev} jobs={jobs}",flush=True)
                if state!="success" or count<=0 or ev!=["collection_attempt_started","collection_success"] or not owned or jobs:
                    raise RuntimeError("resource verification failed")
        if len(events)!=36 or conn.execute(text("SELECT count(*) FROM collection_jobs")).scalar_one():
            raise RuntimeError("unexpected events or jobs")
    print("THREE-SITE LIVE MULTIRESOURCE PASS",flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("command",choices=("prepare","work","verify"))
    p.add_argument("--node",choices=NODES)
    p.add_argument("--execute",action="store_true")
    args=p.parse_args()
    if args.command in ("prepare","work") and not args.execute:
        p.error("--execute required")
    e=engine()
    if args.command=="prepare":prepare(e)
    elif args.command=="work":
        if not args.node:p.error("work requires --node")
        work(e,args.node)
    else:verify(e)
if __name__=="__main__":main()
