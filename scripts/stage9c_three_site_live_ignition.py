"""One-shot three-site REAL Battlelog detailed ignition on isolated Stage 9C D2.

Commands:
  prepare --execute (tcou only; DB must be completely empty)
  work --node tcou|kah-01|hnl-01 --execute (run concurrently on each node)
  verify (read-only)
No production DB, synthetic requests, retries, migrations or worker daemons.
"""
from __future__ import annotations
import argparse
import os
from uuid import uuid5,NAMESPACE_DNS
from sqlalchemy import create_engine,text
from bf4ps.collection_jobs import enqueue_job
from bf4ps.detailed_collector import CollectorIdentity,CollectedJob,collect_one_detailed_job
from scripts.phase4a_cohort import PHASE4A_COHORT

DB="bf4ps_scratch_stage9c_d2"
ROLE="bf4ps_stage9c_d2"
REV="0005_stage9c_dispatch_ledger"
NODES=("tcou","kah-01","hnl-01")
RUN="bf4ps-live-three-site-ignition-20261011-v1"
COHORT=tuple((name,int(persona),NODES[i//3]) for i,(_,persona,name,platform) in enumerate(PHASE4A_COHORT[5:14]))
assert len(COHORT)==9
UUIDS={node:uuid5(NAMESPACE_DNS,RUN+":"+node) for node in NODES}
def engine():
    return create_engine(os.environ["BF4PS_STAGE9C_D2_URL"],pool_pre_ping=True)
def identity(conn):
    db=conn.execute(text("SELECT current_database(),current_user,pg_is_in_recovery(),current_setting('transaction_read_only')")).one()
    rev=conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    if tuple(db)!=(DB,ROLE,False,"off") or rev!=REV:
        raise RuntimeError("REFUSING unexpected database/role/primary/revision")
def inventory(conn):
    return {table:conn.execute(text("SELECT count(*) FROM "+table)).scalar_one()
            for table in ("soldiers","collection_state","collection_jobs","collection_events","collectors")}
def prepare(e):
    with e.begin() as conn:
        identity(conn)
        counts=inventory(conn)
        if any(counts.values()):
            raise RuntimeError(f"REFUSING nonempty D2 database {counts}")
        for node in NODES:
            conn.execute(text("""INSERT INTO collectors
                (collector_uuid,collector_name,hostname,lane,egress_key,enabled,drained)
                VALUES(:id,:name,:host,'background',:egress,true,false)"""),
                {"id":UUIDS[node],"name":RUN+":"+node,"host":node,"egress":RUN+":"+node})
        for name,persona,node in COHORT:
            sid=conn.execute(text("""INSERT INTO soldiers
                (persona_id,platform,current_name,first_seen_at,last_seen_at)
                VALUES(:persona,'pc',:name,now(),now()) RETURNING soldier_id"""),
                {"persona":persona,"name":name}).scalar_one()
            enqueue_job(conn,soldier_id=sid,resource="detailed",lane="background",
                        priority_class="bootstrap",reason=RUN)
    print(f"PREPARE PASS run={RUN} soldiers=9 jobs=9 collectors=3 ceiling=9",flush=True)
def validate(conn):
    identity(conn)
    collectors=conn.execute(text("SELECT collector_uuid,collector_name,hostname,egress_key,lane,enabled,drained,retired_at FROM collectors")).mappings().all()
    if len(collectors)!=3:
        raise RuntimeError("collector count mismatch")
    for c in collectors:
        node=c["hostname"]
        if node not in NODES or c["collector_uuid"]!=UUIDS[node] or c["collector_name"]!=RUN+":"+node or c["egress_key"]!=RUN+":"+node or c["lane"]!="background" or not c["enabled"] or c["drained"] or c["retired_at"] is not None:
            raise RuntimeError("collector identity mismatch")
    soldiers=conn.execute(text("SELECT soldier_id,persona_id,platform,current_name FROM soldiers ORDER BY soldier_id")).mappings().all()
    if len(soldiers)!=9 or {(s["persona_id"],s["platform"],s["current_name"]) for s in soldiers}!={(persona,"pc",name) for name,persona,node in COHORT}:
        raise RuntimeError("soldier cohort mismatch")
    return {s["persona_id"]:s["soldier_id"] for s in soldiers}
def work(e,node):
    if node not in NODES or os.uname().nodename!=node:
        raise RuntimeError("worker hostname mismatch")
    with e.connect() as conn:
        ids=validate(conn)
        allowed=[ids[persona] for name,persona,owner in COHORT if owner==node]
        rows=conn.execute(text("SELECT soldier_id,status FROM collection_jobs WHERE resource='detailed'")).all()
        if any(status not in ("pending","claimed","running") or sid not in ids.values() for sid,status in rows):
            raise RuntimeError("unexpected queue state; stop for inspection")
        own_status={sid:status for sid,status in rows if sid in allowed}
        if len(own_status)!=3 or any(status!="pending" for status in own_status.values()):
            raise RuntimeError("this node's partition already started; refuse re-execution")
        existing=conn.execute(text("SELECT count(*) FROM collection_events WHERE soldier_id=ANY(:ids)"),{"ids":allowed}).scalar_one()
        if existing:
            raise RuntimeError("this node has prior ignition events; refuse re-execution")
    ci=CollectorIdentity(collector_uuid=UUIDS[node],collector_name=RUN+":"+node,
                         hostname=node,egress_key=RUN+":"+node,lane="background")
    for i in range(3):
        result=collect_one_detailed_job(e,identity=ci,request_interval_seconds=10.0,
            allowed_soldier_ids=allowed,max_total_attempts=9,attempts_after_event_id=0,
            attempt_ceiling_resources=["detailed"],enforce_production_budget=True,
            lease_seconds=120,timeout_seconds=30.0,retry_after_seconds=3600)
        print(f"COLLECT node={node} {i+1}/3 {result!r}",flush=True)
        if not isinstance(result,CollectedJob):
            raise RuntimeError("ignition incomplete; no automatic retries")
    print(f"WORKER PASS node={node}",flush=True)
def verify(e):
    with e.connect() as conn:
        ids=validate(conn)
        rows=conn.execute(text("""SELECT s.current_name,s.persona_id,s.soldier_id,
            cs.detailed_state,d.rank,d.kills,d.deaths,
            (SELECT count(*) FROM detailed_stats_history h WHERE h.soldier_id=s.soldier_id) AS history,
            (SELECT count(*) FROM collection_jobs j WHERE j.soldier_id=s.soldier_id) AS jobs
            FROM soldiers s JOIN collection_state cs USING(soldier_id)
            LEFT JOIN detailed_stats_current d USING(soldier_id)
            ORDER BY s.soldier_id""")).mappings().all()
        events=conn.execute(text("""SELECT e.event_type,e.soldier_id,e.collector_uuid
            FROM collection_events e ORDER BY event_id""")).all()
        print(f"VERIFY soldiers={len(rows)} events={len(events)} pending_jobs={conn.execute(text('SELECT count(*) FROM collection_jobs')).scalar_one()}")
        for r in rows:
            owner=next(node for name,persona,node in COHORT if persona==r["persona_id"])
            ev=[t for t,sid,uuid in events if sid==r["soldier_id"]]
            owned=all(uuid==UUIDS[owner] for t,sid,uuid in events if sid==r["soldier_id"])
            print(f"RESULT node={owner} soldier={r['current_name']} state={r['detailed_state']} rank={r['rank']} kills={r['kills']} history={r['history']} events={ev} jobs={r['jobs']}",flush=True)
            if r["detailed_state"]!="success" or r["rank"] is None or r["history"]!=1 or r["jobs"]!=0 or ev!=["collection_attempt_started","collection_success"] or not owned:
                raise RuntimeError("verification incomplete")
        if len(events)!=18 or len(rows)!=9:
            raise RuntimeError("unexpected event or soldier count")
    print("THREE-SITE LIVE IGNITION PASS",flush=True)
def main():
    p=argparse.ArgumentParser()
    p.add_argument("command",choices=("prepare","work","verify"))
    p.add_argument("--node",choices=NODES)
    p.add_argument("--execute",action="store_true")
    args=p.parse_args()
    if args.command in ("prepare","work") and not args.execute:
        p.error("writes and HTTP require --execute")
    e=engine()
    if args.command=="prepare":
        if os.uname().nodename!="tcou":
            raise RuntimeError("prepare only allowed from tcou")
        prepare(e)
    elif args.command=="work":
        if args.node is None: p.error("work requires --node")
        work(e,args.node)
    else:
        verify(e)
if __name__=="__main__":main()
