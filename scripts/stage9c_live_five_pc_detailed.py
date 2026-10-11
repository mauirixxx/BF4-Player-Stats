"""Bounded live five-PC detailed cohort from the frozen Phase 4A identity list.

One-shot scratch integration validation. At most five admitted attempts;
no production activation, no migration, no automatic retry.
"""
from __future__ import annotations
import os
from sqlalchemy import create_engine,text
from bf4ps.collection_jobs import enqueue_job
from bf4ps.detailed_collector import CollectorIdentity,CollectedJob,collect_one_detailed_job

COHORT=(("KamiPebble",1462860155),("MANHUNT1999",1472714233),
        ("HyperMaxZ",1477654907),("LevchenkoBIKS",1479243208),
        ("Peruvian_Baker",1563112811))
EXPECTED=("bf4ps_scratch_stage9c_integration","bf4ps_stage9c_integration",False,"off")
COLLECTOR="live-persistence-validation-tcou"

def main():
    engine=create_engine(os.environ["BF4PS_STAGE9C_INTEGRATION_URL"],pool_pre_ping=True)
    with engine.connect() as conn:
        db=conn.execute(text("SELECT current_database(),current_user,pg_is_in_recovery(),current_setting('transaction_read_only')")).one()
        rev=conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert tuple(db)==EXPECTED and rev=="0004_stage9c_supervision_runs","unexpected DB or revision"
        assert conn.execute(text("SELECT count(*) FROM collection_jobs")).scalar_one()==0,"nonempty queue"
        assert conn.execute(text("SELECT count(*) FROM collectors")).scalar_one()==1,"unexpected collector count"
        collector=conn.execute(text("""SELECT collector_uuid,collector_name,hostname,egress_key,lane,enabled,drained,retired_at,current_job_id
            FROM collectors WHERE collector_name=:name"""),{"name":COLLECTOR}).mappings().one()
        assert (collector["hostname"],collector["egress_key"],collector["lane"])==("tcou","tcou-live-validation","background")
        assert collector["enabled"] and not collector["drained"] and collector["retired_at"] is None and collector["current_job_id"] is None
        for name,persona in COHORT:
            assert conn.execute(text("SELECT count(*) FROM soldiers WHERE persona_id=:p AND platform='pc'"),{"p":persona}).scalar_one()==0
        baseline=conn.execute(text("SELECT coalesce(max(event_id),0) FROM collection_events")).scalar_one()
    print(f"PREFLIGHT PASS cohort={len(COHORT)} max_attempts=5 baseline={baseline}",flush=True)
    with engine.begin() as conn:
        ids=[]
        for name,persona in COHORT:
            sid=conn.execute(text("""INSERT INTO soldiers(persona_id,platform,current_name,first_seen_at,last_seen_at)
                VALUES(:p,'pc',:name,now(),now()) RETURNING soldier_id"""),{"p":persona,"name":name}).scalar_one()
            ids.append(sid)
            enqueue_job(conn,soldier_id=sid,resource="detailed",lane="background",
                        priority_class="bootstrap",reason="bounded_live_five_pc_cohort")
    identity=CollectorIdentity(collector_uuid=collector["collector_uuid"],collector_name=collector["collector_name"],
                               hostname=collector["hostname"],egress_key=collector["egress_key"],lane="background")
    results=[]
    for n in range(len(ids)):
        result=collect_one_detailed_job(engine,identity=identity,request_interval_seconds=10.0,
                allowed_soldier_ids=ids,max_total_attempts=5,attempts_after_event_id=baseline,
                attempt_ceiling_resources=["detailed"],enforce_production_budget=True,
                lease_seconds=120,timeout_seconds=15.0,retry_after_seconds=3600)
        print(f"COLLECT {n+1}/5 {result!r}",flush=True)
        results.append(result)
        if not isinstance(result,CollectedJob):
            print("STOP: non-successful result; no further requests",flush=True)
            break
    with engine.connect() as conn:
        for (name,persona),sid in zip(COHORT,ids):
            row=conn.execute(text("""SELECT cs.detailed_state,d.rank,d.kills,d.deaths
                FROM collection_state cs LEFT JOIN detailed_stats_current d USING(soldier_id)
                WHERE cs.soldier_id=:sid"""),{"sid":sid}).one()
            history=conn.execute(text("SELECT count(*) FROM detailed_stats_history WHERE soldier_id=:sid"),{"sid":sid}).scalar_one()
            events=conn.execute(text("""SELECT event_type FROM collection_events WHERE soldier_id=:sid AND event_id>:baseline
                ORDER BY event_id"""),{"sid":sid,"baseline":baseline}).scalars().all()
            jobs=conn.execute(text("SELECT count(*) FROM collection_jobs WHERE soldier_id=:sid"),{"sid":sid}).scalar_one()
            print(f"VERIFY {name} persona={persona} state={row[0]} rank={row[1]} kills={row[2]} deaths={row[3]} history={history} events={events} jobs={jobs}",flush=True)
            if len(results)==len(ids) and all(isinstance(r,CollectedJob) for r in results):
                assert row[0]=="success" and history==1 and jobs==0
                assert events==["collection_attempt_started","collection_success"]
    if len(results)!=len(ids) or not all(isinstance(r,CollectedJob) for r in results):
        raise SystemExit("cohort incomplete; inspect DB before resuming")
    print("FIVE-PC LIVE DETAILED COHORT PASS",flush=True)

if __name__=="__main__": main()
