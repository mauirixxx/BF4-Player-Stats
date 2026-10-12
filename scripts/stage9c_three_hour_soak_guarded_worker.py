"""Isolated D2 guarded soak worker; no automatic ignition."""
import argparse
import os
import time
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError, TimeoutError as SQLAlchemyTimeoutError
from bf4ps.detailed_collector import CollectorIdentity, collect_one_detailed_job
from scripts.stage9c_three_site_live_ignition import engine, NODES, RUN, UUIDS, COHORT
from scripts.stage9c_three_hour_soak_cohort import cohort_ids
from scripts.stage9c_three_hour_soak_ledger import RUN_ID, BASELINE_EVENT, MAX_ATTEMPTS, guard
from scripts.stage9c_three_hour_soak_http_gate import admit_physical_start

def preflight(conn,node):
    guard(conn)
    ids=cohort_ids(conn)
    run=conn.execute(text("SELECT state,deadline_at FROM soak_runs WHERE run_id=:run"),
                     {"run":RUN_ID}).one_or_none()
    if run is None or run.state!="running" or run.deadline_at is None:
        raise RuntimeError("SOAK BLOCK: run not running")
    if conn.execute(text("SELECT clock_timestamp()")).scalar_one()>=run.deadline_at:
        raise RuntimeError("SOAK BLOCK: deadline expired")
    if not conn.execute(text(
        "SELECT 1 FROM soak_rounds WHERE run_id=:run AND state='enqueued'"),
        {"run":RUN_ID}).first():
        raise RuntimeError("SOAK BLOCK: no enqueued round")
    return ids

def soak_engine():
    """Bound one D2 worker process to one pooled database connection."""
    return create_engine(os.environ["BF4PS_STAGE9C_D2_URL"], pool_size=1,
                         max_overflow=0, pool_timeout=5, pool_pre_ping=True)

def work(node, *, db_engine=None):
    if node not in NODES or os.uname().nodename!=node:
        raise RuntimeError("SOAK BLOCK: hostname mismatch")
    owned = db_engine is None
    e = soak_engine() if owned else db_engine
    try:
        return _work_with_engine(node, e)
    finally:
        if owned:
            e.dispose()

def preflight_with_db_retry(e, node, *, attempts=3, sleep=time.sleep):
    """Retry DB-only preflight; NEVER replay the HTTP-capable collector."""
    for index in range(attempts):
        try:
            with e.connect() as conn:
                return preflight(conn, node)
        except (OperationalError, SQLAlchemyTimeoutError):
            if index + 1 == attempts:
                raise
            sleep(min(2 ** index, 4))

def _work_with_engine(node, e):
    ids=preflight_with_db_retry(e,node)
    permitted_personas={persona for _,persona,owner in COHORT if owner==node}
    if len(permitted_personas)!=3:
        raise RuntimeError('SOAK BLOCK: invalid site partition')
    with e.connect() as conn:
        rows=conn.execute(text('SELECT soldier_id,persona_id FROM soldiers')).all()
    by_persona={int(persona):int(sid) for sid,persona in rows}
    if len(rows)!=9 or len(by_persona)!=9 or set(by_persona.values())!=set(ids):
        raise RuntimeError('SOAK BLOCK: invalid soldier mapping')
    permitted_ids=sorted(by_persona[p] for p in permitted_personas)
    identity=CollectorIdentity(
        collector_uuid=UUIDS[node],collector_name=RUN+":"+node,
        hostname=node,egress_key=RUN+":"+node,lane="background")
    return collect_one_detailed_job(
        e,identity=identity,request_interval_seconds=10.0,
        allowed_soldier_ids=permitted_ids,max_total_attempts=MAX_ATTEMPTS,
        attempts_after_event_id=BASELINE_EVENT,
        attempt_ceiling_resources=["detailed"],
        enforce_production_budget=True,lease_seconds=120,
        timeout_seconds=30.0,retry_after_seconds=3600,
        pre_http_admission=admit_physical_start)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("command",choices=("preflight","work"))
    p.add_argument("--node",required=True,choices=NODES)
    p.add_argument("--execute",action="store_true")
    a=p.parse_args()
    if a.command=="work" and not a.execute:
        p.error("work requires --execute")
    if a.command=="preflight":
        e = soak_engine()
        try:
            with e.connect() as conn:
                preflight(conn,a.node)
        finally:
            e.dispose()
        print("SOAK PREFLIGHT PASS",a.node)
    else:
        print("SOAK WORKER RESULT",work(a.node),flush=True)

if __name__=="__main__":
    main()
