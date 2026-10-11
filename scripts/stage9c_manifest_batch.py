"""Restart-safe bounded Stage 9C live batch for existing soldier identities.

init creates an immutable run file; run and verify use the same event baseline
and global attempt ceiling. No new identities, production workers or migrations.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
from sqlalchemy import create_engine,text
from bf4ps.collection_jobs import enqueue_job
from bf4ps.detailed_collector import CollectorIdentity as DI, CollectedJob, collect_one_detailed_job
from bf4ps.weapon_collector import CollectorIdentity as WI, CollectedWeaponJob, collect_one_weapon_job
from bf4ps.vehicle_collector import CollectorIdentity as VI, CollectedVehicleJob, collect_one_vehicle_job
from scripts.stage9c_batch_preflight import parse_manifest,EXPECTED_DB,EXPECTED_ROLE,EXPECTED_REVISION

COLLECTOR="live-persistence-validation-tcou"
IMPLEMENTATIONS={"detailed":(DI,CollectedJob,collect_one_detailed_job),
                 "weapons":(WI,CollectedWeaponJob,collect_one_weapon_job),
                 "vehicles":(VI,CollectedVehicleJob,collect_one_vehicle_job)}
TABLES={"detailed":"detailed_stats_current","weapons":"soldier_weapon_stats",
        "vehicles":"soldier_vehicle_stats"}

def target(engine):
    with engine.connect() as conn:
        db=conn.execute(text("SELECT current_database(),current_user,pg_is_in_recovery(),current_setting('transaction_read_only')")).one()
        rev=conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        if tuple(db)!=(EXPECTED_DB,EXPECTED_ROLE,False,"off") or rev!=EXPECTED_REVISION:
            raise RuntimeError("unexpected DB identity or migration")
        collectors=conn.execute(text("""SELECT collector_uuid,collector_name,hostname,egress_key,lane,
            enabled,drained,retired_at,current_job_id FROM collectors""")).mappings().all()
        if len(collectors)!=1:
            raise RuntimeError("unexpected collector inventory")
        c=collectors[0]
        if not (c["collector_name"]==COLLECTOR and c["hostname"]=="tcou" and
                c["egress_key"]=="tcou-live-validation" and c["lane"]=="background"
                and c["enabled"] and not c["drained"] and c["retired_at"] is None
                and c["current_job_id"] is None):
            raise RuntimeError("unexpected collector state")
        return dict(c)

def resolved(conn,soldiers):
    result=[]
    for platform,persona in soldiers:
        row=conn.execute(text("""SELECT s.soldier_id FROM soldiers s
            JOIN collection_state cs USING(soldier_id)
            WHERE s.platform=:p AND s.persona_id=:id"""),{"p":platform,"id":persona}).one_or_none()
        if row is None:
            raise RuntimeError(f"missing soldier {platform}/{persona}; no implicit registration")
        result.append(int(row.soldier_id))
    return result

def check_queue(conn,ids,resources):
    jobs=conn.execute(text("""SELECT soldier_id,resource,status FROM collection_jobs""")).mappings().all()
    if any(j["soldier_id"] not in ids or j["resource"] not in resources or
           j["status"]!="pending" for j in jobs):
        raise RuntimeError("unrelated or owned jobs exist; refusing batch")

def load(path):
    data=json.loads(path.read_text())
    soldiers,resources,limit=parse_manifest(data)
    if data.get("expected_database")!=EXPECTED_DB or data.get("expected_revision")!=EXPECTED_REVISION:
        raise RuntimeError("manifest DB/revision mismatch")
    baseline=data.get("baseline_event_id")
    if type(baseline) is not int or baseline<0:
        raise RuntimeError("missing immutable baseline")
    if data.get("collector")!=COLLECTOR:
        raise RuntimeError("unexpected manifest collector")
    return data,soldiers,resources,limit,baseline

def initialize(engine,source,destination):
    if destination.exists():
        raise RuntimeError("manifest already exists; never reset baseline")
    data=json.loads(source.read_text())
    soldiers,resources,limit=parse_manifest(data)
    target(engine)
    with engine.connect() as conn:
        ids=resolved(conn,soldiers)
        check_queue(conn,ids,resources)
        for sid in ids:
            for resource in resources:
                state=conn.execute(text("SELECT "+resource+"_state FROM collection_state WHERE soldier_id=:id"),{"id":sid}).scalar_one()
                if state not in ("never_attempted","success"):
                    raise RuntimeError(f"unsafe state {sid}/{resource}={state}")
        baseline=conn.execute(text("SELECT coalesce(max(event_id),0) FROM collection_events")).scalar_one()
    data=dict(data,expected_database=EXPECTED_DB,expected_revision=EXPECTED_REVISION,
              collector=COLLECTOR,baseline_event_id=int(baseline))
    # Exclusive create ensures accidental reruns cannot reset the durable ceiling.
    with destination.open("x") as handle:
        json.dump(data,handle,indent=2,sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    print(f"INIT PASS manifest={destination} soldiers={len(ids)} resources={resources} "
          f"max_attempts={limit} baseline={baseline}",flush=True)

def snapshot(engine,ids,resources,baseline):
    with engine.connect() as conn:
        check_queue(conn,ids,resources)
        attempts=conn.execute(text("""SELECT COUNT(DISTINCT (job_id,attempt_number))
            FROM collection_events WHERE event_id>:baseline
            AND event_type IN ('collection_attempt_started','collection_success',
                               'collection_failure','collection_persistence_failure')
            AND soldier_id=ANY(:ids) AND resource=ANY(:resources)
            AND job_id IS NOT NULL AND attempt_number IS NOT NULL"""),
            {"baseline":baseline,"ids":ids,"resources":list(resources)}).scalar_one()
        rows=[]
        for sid in ids:
            for resource in resources:
                state=conn.execute(text("SELECT "+resource+"_state FROM collection_state WHERE soldier_id=:id"),{"id":sid}).scalar_one()
                count=conn.execute(text("SELECT count(*) FROM "+TABLES[resource]+" WHERE soldier_id=:id"),{"id":sid}).scalar_one()
                events=conn.execute(text("""SELECT event_type FROM collection_events
                    WHERE event_id>:baseline AND soldier_id=:id AND resource=:resource
                    ORDER BY event_id"""),{"baseline":baseline,"id":sid,"resource":resource}).scalars().all()
                jobs=conn.execute(text("""SELECT count(*) FROM collection_jobs
                    WHERE soldier_id=:id AND resource=:resource"""),{"id":sid,"resource":resource}).scalar_one()
                rows.append((sid,resource,state,count,events,jobs))
        return int(attempts),rows

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("command",choices=("init","run","verify"))
    parser.add_argument("--manifest",required=True,type=Path)
    parser.add_argument("--source",type=Path,help="source manifest JSON for init")
    args=parser.parse_args()
    engine=create_engine(os.environ["BF4PS_STAGE9C_INTEGRATION_URL"],pool_pre_ping=True)
    if args.command=="init":
        if args.source is None:
            parser.error("init requires --source")
        initialize(engine,args.source,args.manifest)
        return
    data,soldiers,resources,limit,baseline=load(args.manifest)
    collector=target(engine)
    with engine.connect() as conn:
        ids=resolved(conn,soldiers)
    attempts,rows=snapshot(engine,ids,resources,baseline)
    if args.command=="verify":
        print(f"VERIFY attempts={attempts}/{limit} baseline={baseline}")
        for sid,resource,state,count,events,jobs in rows:
            print(f"RESOURCE soldier={sid} resource={resource} state={state} rows={count} events={events} jobs={jobs}")
        return
    if attempts>=limit:
        raise RuntimeError("attempt budget exhausted")
    if any(jobs for _,_,_,_,_,jobs in rows):
        raise RuntimeError("existing queued work requires operator inspection before run")
    pending=[(sid,resource) for sid,resource,state,count,_,_ in rows if state=="never_attempted"]
    if not pending:
        print("NO-OP: all resources already collected",flush=True)
        return
    if len(pending)>limit-attempts:
        raise RuntimeError("remaining attempt budget cannot cover all pending resources")
    with engine.begin() as conn:
        for sid,resource in pending:
            enqueue_job(conn,soldier_id=sid,resource=resource,lane="background",
                        priority_class="bootstrap",reason="bounded_manifest_batch")
    for resource in resources:
        cls,success,collect=IMPLEMENTATIONS[resource]
        identity=cls(collector_uuid=collector["collector_uuid"],collector_name=collector["collector_name"],
                     hostname=collector["hostname"],egress_key=collector["egress_key"],lane="background")
        for _ in range(sum(1 for _,r in pending if r==resource)):
            result=collect(engine,identity=identity,request_interval_seconds=10.0,
                allowed_soldier_ids=ids,max_total_attempts=limit,
                attempts_after_event_id=baseline,attempt_ceiling_resources=list(resources),
                enforce_production_budget=True,lease_seconds=120,
                timeout_seconds=30.0,retry_after_seconds=3600)
            print(f"COLLECT {resource}: {result!r}",flush=True)
            if not isinstance(result,success):
                raise RuntimeError("collection incomplete; inspect events/queue; no automatic retry")
    attempts,rows=snapshot(engine,ids,resources,baseline)
    for sid,resource,state,count,events,jobs in rows:
        print(f"VERIFY soldier={sid} resource={resource} state={state} rows={count} jobs={jobs}",flush=True)
        if state!="success" or count==0 or jobs!=0:
            raise RuntimeError("post-collection verification failed")
    print(f"MANIFEST LIVE BATCH PASS attempts={attempts}/{limit}",flush=True)

if __name__=="__main__":
    main()
