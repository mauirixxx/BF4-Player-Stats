"""Explicitly authorized D2 3-hour soak supervisor; isolated DB only."""
import argparse,os,time,traceback
from sqlalchemy import text
from scripts.stage9c_three_site_live_ignition import engine,NODES
from scripts.stage9c_three_hour_soak_cohort import cohort_ids
from scripts.stage9c_three_hour_soak_ledger import RUN_ID,ROUNDS,ROUND_SECONDS,create_prepared_run,admit_round,guard
from scripts.stage9c_three_hour_soak_lifecycle import ignite,stop
from scripts.stage9c_three_hour_soak_reconcile import reconcile
from scripts.stage9c_three_hour_soak_guarded_worker import work,soak_engine

def supervisor():
    if os.uname().nodename!="tcou":raise RuntimeError("coordinator must be tcou")
    e=soak_engine()
    with e.begin() as c:
        ids=cohort_ids(c)
        create_prepared_run(c,ids)
        info=ignite(c,ids)
        admit_round(c,ids,1)
    print("SOAK IGNITED",info,flush=True)
    current=1
    while True:
        try:
            with e.begin() as c:
                guard(c)
                run=c.execute(text("SELECT state,start_at,deadline_at FROM soak_runs WHERE run_id=:r FOR UPDATE"),{"r":RUN_ID}).one()
                now=c.execute(text("SELECT clock_timestamp()")).scalar_one()
                if run.state!="running" or now>=run.deadline_at:
                    if run.state=="running":stop(c,"three-hour deadline reached")
                    print("SOAK STOP",run.state,flush=True)
                    break
                outcome=reconcile(c,current)
                if outcome["state"]=="completed" and current<ROUNDS:
                    eligible=run.start_at.timestamp()+current*ROUND_SECONDS
                    if now.timestamp()>=eligible:
                        admit_round(c,ids,current+1)
                        current+=1
                        print("SOAK ROUND ENQUEUED",current,flush=True)
                if outcome["anomalies"]:
                    stop(c,"reconciliation anomalies")
                    raise RuntimeError(str(outcome["anomalies"]))
            time.sleep(5)
        except Exception as exc:
            print("SOAK COORDINATOR ERROR",repr(exc),flush=True)
            with e.begin() as c:
                stop(c,"coordinator failure: "+str(exc)[:200])
            raise

def worker_loop(node):
    if os.uname().nodename!=node:raise RuntimeError("hostname mismatch")
    e=soak_engine()
    try:
        _worker_loop_with_engine(node,e)
    finally:
        e.dispose()

def _worker_loop_with_engine(node,e):
    while True:
        try:
            result=work(node,db_engine=e)
            if result is not None:print("SOAK WORK",node,repr(result),flush=True)
            else:time.sleep(3)
        except RuntimeError as exc:
            if str(exc) in ("SOAK BLOCK: run not running","SOAK BLOCK: deadline expired"):
                print("SOAK WORKER STOP",node,str(exc),flush=True)
                return
            if str(exc)=="SOAK BLOCK: no enqueued round":
                time.sleep(3)
                continue
            print("SOAK WORKER ERROR",node,repr(exc),flush=True)
            raise

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("mode",choices=("coordinator","worker"))
    p.add_argument("--node",choices=NODES)
    p.add_argument("--execute",action="store_true")
    a=p.parse_args()
    if not a.execute: p.error("explicit --execute required")
    if a.mode=="coordinator":supervisor()
    elif not a.node:p.error("--node required")
    else:worker_loop(a.node)
