#!/usr/bin/env python3
"""T4 scratch-only coordinator: seed, inspect, cleanup. No HTTP or remote execution."""
from __future__ import annotations
import argparse
import os
from uuid import UUID, uuid4
from sqlalchemy import create_engine, text
from bf4ps.background_service import BACKGROUND_SLOTS_PER_HOUR, _usage
from scripts.phase5b_stage9c_abort_drain_scratch import check
from scripts.phase5b_stage9c_t4_barrier import READY, RELEASE, DONE, events, emit, verify_ready, verify_done
from scripts.phase5b_stage9c_postgres_integration import refuse_unsafe_target
from scripts.phase5b_stage9c_t4_recovery_rules import validate_partial_ledger

HOSTS = ("tcou", "hnl-01", "kah-01")
TABLES = ("collectors", "soldiers", "collection_jobs", "collection_events", "stage9c_supervision_runs")

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("seed", "release", "inspect", "cleanup", "recover"))
    p.add_argument("--execute", action="store_true")
    p.add_argument("--confirm-all-participants-stopped", action="store_true",
                   help="Required for recovery; operator has verified all three processes exited")
    p.add_argument("--confirm-preserved-evidence", action="store_true",
                   help="Required for recovery; diagnostic output and host logs saved externally")
    p.add_argument("--run-id", help="UUID printed by seed; required for inspect/cleanup")
    args = p.parse_args()
    if not args.execute:
        p.error("explicit --execute required")
    if args.action != "seed" and not args.run_id:
        p.error("--run-id required")
    if args.action == "recover" and not (args.confirm_all_participants_stopped and args.confirm_preserved_evidence):
        p.error("recovery requires explicit stopped-participants and preserved-evidence confirmations")
    url = os.environ.get("BF4PS_STAGE9C_INTEGRATION_URL", "")
    refuse_unsafe_target(url)
    engine = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout":5,"options":"-c statement_timeout=15000"})
    marker = "stage9c_t4_" + (str(UUID(args.run_id)) if args.run_id else str(uuid4()))
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
                jobs_seeded = []
                for index, host in enumerate(HOSTS):
                    sid = conn.execute(text("""
                    INSERT INTO soldiers(persona_id,platform,current_name,first_seen_at,last_seen_at)
                    VALUES (:persona,'pc',:name,now(),now()) RETURNING soldier_id
                """), {"persona":880000000000+int(uuid4().int%100000000),"name":marker+"_"+host}).scalar_one()
                    jid = conn.execute(text("""
                    INSERT INTO collection_jobs(soldier_id,resource,lane,priority_class,reason,status,priority_value,eligible_at)
                    VALUES (:sid,'detailed','background','active',:marker,'pending',0,now())
                    RETURNING job_id
                """), {"sid":sid,"marker":marker}).scalar_one()
                    jobs_seeded.append((jid,sid))
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
                print("Jobs and soldiers:",jobs_seeded)
                print("Participant UUIDs:",*(f"{h}={u}" for h,u in ids.items()))
                print("NOT AUTHORIZED TO RUN REMOTELY UNTIL OPERATOR APPROVES")
            else:
                rows = conn.execute(text("""
                    SELECT j.job_id,j.soldier_id,j.status,j.collector_uuid,j.attempt_count
                    FROM collection_jobs j WHERE j.reason=:marker
                """), {"marker":marker}).all()
                if len(rows)!=3 or len({r.soldier_id for r in rows})!=3:
                    raise RuntimeError(f"REFUSING unexpected fixture jobs: {len(rows)}")
                owners = conn.execute(text("""
                    SELECT collector_uuid,hostname FROM collectors
                    WHERE collector_name IN (:tcou,:hnl,:kah) ORDER BY hostname
                """), {"tcou":marker+"_tcou","hnl":marker+"_hnl-01","kah":marker+"_kah-01"}).all()
                if len(owners)!=3 or {x.hostname for x in owners}!=set(HOSTS):
                    raise RuntimeError("REFUSING collector identity drift")
                if args.action=="release":
                    verify_ready(conn, marker)
                    if events(conn,marker,RELEASE) or events(conn,marker,DONE):
                        raise RuntimeError("REFUSING duplicate/late release")
                    if any(j.status!="pending" or j.attempt_count!=0 for j in rows):
                        raise RuntimeError("REFUSING release after claim")
                    if _usage(conn).total!=BACKGROUND_SLOTS_PER_HOUR-1:
                        raise RuntimeError("REFUSING changed budget before release")
                    window = conn.execute(text("""
                        SELECT COUNT(*) AS n, MIN(occurred_at) AS oldest,
                               MAX(occurred_at) AS newest
                        FROM collection_events
                        WHERE metadata->>'stage9c_t4_marker'=:marker
                          AND event_type='collection_attempt_started'
                    """), {"marker":marker}).one()
                    if window.n != BACKGROUND_SLOTS_PER_HOUR-1:
                        raise RuntimeError("REFUSING changed synthetic event count")
                    if not conn.execute(text("""
                        SELECT CAST(:oldest AS timestamptz) >= now() - interval '5 minutes'
                    """), {"oldest":window.oldest}).scalar_one():
                        raise RuntimeError("REFUSING stale synthetic budget window")
                    emit(conn,marker,RELEASE)
                    print("PASS: three hosts ready; release committed")
                elif args.action=="inspect":
                    verify_ready(conn,marker)
                    verify_done(conn,marker)
                    if len(events(conn,marker,RELEASE))!=1:
                        raise AssertionError("release ledger mismatch")
                    usage=_usage(conn)
                    print("JOBS",rows)
                    print("USAGE",usage)
                    winners=[j for j in rows if j.status=="claimed" and j.attempt_count==1 and j.collector_uuid in {x.collector_uuid for x in owners}]
                    pending=[j for j in rows if j.status=="pending" and j.attempt_count==0]
                    if len(winners)!=1 or len(pending)!=2:
                        raise AssertionError("three independent jobs did not yield exactly one reservation")
                    if usage.total!=BACKGROUND_SLOTS_PER_HOUR:
                        raise AssertionError("budget incorrect after winner reservation")
                    print("PASS: one claimed job, 1296/1296 used (host logs still required)")
                else:
                    if args.action=="cleanup":
                        verify_ready(conn,marker)
                        verify_done(conn,marker)
                        if len(events(conn,marker,RELEASE))!=1:
                            raise RuntimeError("REFUSING cleanup without exactly one release")
                    else:
                        # Recovery deliberately supports partial READY/RELEASE/DONE ledgers.
                        # Never silently remove a complete run via the recovery path.
                        ready, released, done = (events(conn,marker,k) for k in (READY,RELEASE,DONE))
                        validate_partial_ledger(ready, released, done, rows)
                        print("RECOVERY: partial ledger accepted only after operator confirmations")
                    # Refuse cleanup until any winning lease has expired.
                    # Operator must first confirm all participants exited.
                    for job in rows:
                        if job.status in ("claimed", "running"):
                            expired = conn.execute(text(
                                "SELECT lease_expires_at <= now() FROM collection_jobs WHERE job_id=:jid"
                            ), {"jid":job.job_id}).scalar_one()
                            if not expired:
                                raise RuntimeError("REFUSING cleanup of unexpired lease")
                    # Remove events before jobs: FK ON DELETE SET NULL.
                    counts=conn.execute(text("""
                        SELECT event_type,COUNT(*) AS n FROM collection_events
                        WHERE metadata->>'stage9c_t4_marker'=:marker
                        GROUP BY event_type
                    """), {"marker":marker}).all()
                    observed={x.event_type:x.n for x in counts}
                    allowed={"collection_attempt_started",READY,RELEASE,DONE}
                    if set(observed)-allowed or observed.get("collection_attempt_started")!=BACKGROUND_SLOTS_PER_HOUR-1:
                        raise RuntimeError(f"REFUSING unexpected event types/counts: {observed}")
                    expected=BACKGROUND_SLOTS_PER_HOUR-1+sum(observed.get(k,0) for k in (READY,RELEASE,DONE))
                    if args.action=="cleanup" and expected!=BACKGROUND_SLOTS_PER_HOUR-1+7:
                        raise RuntimeError("REFUSING unexpected complete-run ledger counts")
                    n=conn.execute(text("""
                        DELETE FROM collection_events WHERE metadata->>'stage9c_t4_marker'=:marker
                    """), {"marker":marker}).rowcount
                    if n!=expected:
                        raise RuntimeError(f"REFUSING unexpected fixture event count {n}; expected {expected}")
                    n=conn.execute(text("DELETE FROM collection_jobs WHERE reason=:marker"),
                                   {"marker":marker}).rowcount
                    if n!=3: raise RuntimeError("REFUSING job cleanup mismatch")
                    n=conn.execute(text("DELETE FROM soldiers WHERE current_name IN (:tcou,:hnl,:kah)"),
                                   {"tcou":marker+"_tcou","hnl":marker+"_hnl-01","kah":marker+"_kah-01"}).rowcount
                    if n!=3: raise RuntimeError("REFUSING soldier cleanup mismatch")
                    n=conn.execute(text("DELETE FROM collectors WHERE collector_name IN (:tcou,:hnl,:kah)"),
                                   {"tcou":marker+"_tcou","hnl":marker+"_hnl-01","kah":marker+"_kah-01"}).rowcount
                    if n!=3: raise RuntimeError("REFUSING collector cleanup mismatch")
                    print("PASS: exact T4 fixture cleanup; independent census still required")
    finally:
        engine.dispose()
if __name__=="__main__":
    main()
