"""Isolated D2 guarded soak worker; no automatic ignition."""
import argparse
import os
from sqlalchemy import text
from bf4ps.detailed_collector import CollectorIdentity, collect_one_detailed_job
from scripts.stage9c_three_site_live_ignition import engine, NODES, RUN, UUIDS
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

def work(node):
    if node not in NODES or os.uname().nodename!=node:
        raise RuntimeError("SOAK BLOCK: hostname mismatch")
    e=engine()
    with e.connect() as conn:
        ids=preflight(conn,node)
    identity=CollectorIdentity(
        collector_uuid=UUIDS[node],collector_name=RUN+":"+node,
        hostname=node,egress_key=RUN+":"+node,lane="background")
    return collect_one_detailed_job(
        e,identity=identity,request_interval_seconds=10.0,
        allowed_soldier_ids=ids,max_total_attempts=MAX_ATTEMPTS,
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
        with engine().connect() as conn:
            preflight(conn,a.node)
        print("SOAK PREFLIGHT PASS",a.node)
    else:
        print("SOAK WORKER RESULT",work(a.node),flush=True)

if __name__=="__main__":
    main()
