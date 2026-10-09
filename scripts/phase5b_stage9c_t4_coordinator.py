#!/usr/bin/env python3
"""T4 scratch-only coordinator: seed, inspect, cleanup. No HTTP or remote execution."""
from __future__ import annotations
import argparse
import os
from uuid import uuid4
from sqlalchemy import create_engine, text
from bf4ps.background_service import BACKGROUND_SLOTS_PER_HOUR, _usage
from scripts.phase5b_stage9c_abort_drain_scratch import check
from scripts.phase5b_stage9c_postgres_integration import refuse_unsafe_target

HOSTS = ("tcou", "hnl-01", "kah-01")
TABLES = ("collectors", "soldiers", "collection_jobs", "collection_events", "stage9c_supervision_runs")

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("seed", "inspect", "cleanup"))
    p.add_argument("--execute", action="store_true")
    p.add_argument("--run-id", help="UUID printed by seed; required for inspect/cleanup")
    args = p.parse_args()
    if not args.execute:
        p.error("explicit --execute required")
    if args.action != "seed" and not args.run_id:
        p.error("--run-id required")
    url = os.environ.get("BF4PS_STAGE9C_INTEGRATION_URL", "")
    refuse_unsafe_target(url)
    engine = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout":5,"options":"-c statement_timeout=15000"})
    marker = "stage9c_t4_" + (args.run_id or str(uuid4()))
    try:
        with engine.begin() as conn:
            if args.action == "seed":
                check(conn)
            else:
                from scripts.phase5b_stage9c_postgres_integration import EXPECTED_DATABASE, EXPECTED_IP, EXPECTED_USER
                ident = conn.execute(text("SELECT current_database(),current_user,inet_server_addr(),pg_is_in_recovery(),current_setting('transaction_read_only')")).one()
                if (ident[0],ident[1],str(ident[2]),ident[3],ident[4]) != (EXPECTED_DATABASE,EXPECTED_USER,EXPECTED_IP,False,"off"):
                    raise RuntimeError("REFUSING scratch identity drift")
                rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                if rev != "0004_stage9c_supervision_runs":
                    raise RuntimeError("REFUSING revision drift")
            conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('bf4ps:stage9c-reservation-start-fixture'))"))
            if args.action == "seed":
                for table in TABLES:
                    if conn.execute(text(f"SELECT count(*) FROM public.{table}")).scalar_one():
                        raise RuntimeError(f"REFUSING nonempty {table}")
                ids = {}
                for host in HOSTS:
                    uid = uuid4()
                    ids[host] = uid
                    conn.execute(text("""
                        INSERT INTO collectors
                        (collector_uuid,collector_name,hostname,lane,egress_key,enabled,drained,heartbeat_state)
                        VALUES (:uid,:name,:host,'background',:egress,true,false,'healthy')
                    """), {"uid":uid,"name":marker+"_"+host,"host":host,"egress":marker+"_"+host})
                sid = conn.execute(text("""
                    INSERT INTO soldiers(persona_id,platform,current_name,first_seen_at,last_seen_at)
                    VALUES (:persona,'pc',:name,now(),now()) RETURNING soldier_id
                """), {"persona":880000000000+int(uuid4().int%100000000),"name":marker}).scalar_one()
                jid = conn.execute(text("""
                    INSERT INTO collection_jobs(soldier_id,resource,lane,priority_class,reason,status,priority_value,eligible_at)
                    VALUES (:sid,'detailed','background','active',:marker,'pending',0,now())
                    RETURNING job_id
                """), {"sid":sid,"marker":marker}).scalar_one()
                conn.execute(text("""
                    INSERT INTO collection_events(resource,lane,event_type,attempt_number,metadata)
                    SELECT 'detailed','background','collection_attempt_started',1,
                      jsonb_build_object('stage9c_t4_marker',CAST(:marker AS text),
                                         'priority_class','active','retry',false)
                    FROM generate_series(1,:n)
                """), {"marker":marker,"n":BACKGROUND_SLOTS_PER_HOUR-1})
                if _usage(conn).total != BACKGROUND_SLOTS_PER_HOUR-1:
                    raise AssertionError("fixture did not create 1295 used slots")
                print("SEEDED run-id:",marker.removeprefix("stage9c_t4_"))
                print("Job:",jid,"Soldier:",sid)
                print("Participant UUIDs:",*(f"{h}={u}" for h,u in ids.items()))
                print("NOT AUTHORIZED TO RUN REMOTELY UNTIL OPERATOR APPROVES")
            else:
                rows = conn.execute(text("""
                    SELECT j.job_id,j.soldier_id,j.status,j.collector_uuid,j.attempt_count
                    FROM collection_jobs j WHERE j.reason=:marker
                """), {"marker":marker}).all()
                if len(rows)!=1:
                    raise RuntimeError(f"REFUSING unexpected fixture job count: {len(rows)}")
                job = rows[0]
                owners = conn.execute(text("""
                    SELECT collector_uuid,hostname FROM collectors
                    WHERE collector_name LIKE :prefix ORDER BY hostname
                """), {"prefix":marker+"_%"}).all()
                if len(owners)!=3 or {x.hostname for x in owners}!=set(HOSTS):
                    raise RuntimeError("REFUSING collector identity drift")
                if args.action=="inspect":
                    usage=_usage(conn)
                    print("JOB",job)
                    print("USAGE",usage)
                    if job.status!="claimed" or job.attempt_count!=1 or job.collector_uuid not in {x.collector_uuid for x in owners}:
                        raise AssertionError("cross-host claim outcome not established")
                    if usage.total!=BACKGROUND_SLOTS_PER_HOUR:
                        raise AssertionError("budget incorrect after winner reservation")
                    print("PASS: one claimed job, 1296/1296 used (host logs still required)")
                else:
                    # Remove events before jobs: FK ON DELETE SET NULL.
                    n=conn.execute(text("""
                        DELETE FROM collection_events WHERE metadata->>'stage9c_t4_marker'=:marker
                    """), {"marker":marker}).rowcount
                    if n!=BACKGROUND_SLOTS_PER_HOUR-1:
                        raise RuntimeError(f"REFUSING unexpected synthetic event count {n}")
                    n=conn.execute(text("DELETE FROM collection_jobs WHERE job_id=:jid AND reason=:marker"),
                                   {"jid":job.job_id,"marker":marker}).rowcount
                    if n!=1: raise RuntimeError("REFUSING job cleanup mismatch")
                    n=conn.execute(text("DELETE FROM soldiers WHERE soldier_id=:sid AND current_name=:marker"),
                                   {"sid":job.soldier_id,"marker":marker}).rowcount
                    if n!=1: raise RuntimeError("REFUSING soldier cleanup mismatch")
                    n=conn.execute(text("DELETE FROM collectors WHERE collector_name LIKE :prefix"),
                                   {"prefix":marker+"_%"}).rowcount
                    if n!=3: raise RuntimeError("REFUSING collector cleanup mismatch")
                    print("PASS: exact T4 fixture cleanup; independent census still required")
    finally:
        engine.dispose()
if __name__=="__main__":
    main()
