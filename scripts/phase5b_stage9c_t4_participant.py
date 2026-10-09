#!/usr/bin/env python3
"""T4 one-shot scratch admission participant. No HTTP; operator approval required."""
from __future__ import annotations
import argparse
import os
import socket
import time
from uuid import UUID
from sqlalchemy import create_engine, text
from bf4ps.background_service import claim_production_background_job
from scripts.phase5b_stage9c_t4_barrier import READY, RELEASE, DONE, events, emit
from scripts.phase5b_stage9c_postgres_integration import (
    EXPECTED_DATABASE,EXPECTED_IP,EXPECTED_USER,refuse_unsafe_target,
)

HOSTS = {"tcou","hnl-01","kah-01"}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--expected-host",required=True,choices=sorted(HOSTS))
    p.add_argument("--run-id",required=True)
    p.add_argument("--execute",action="store_true")
    args=p.parse_args()
    if not args.execute: p.error("--execute required; requires operator approval")
    actual=socket.gethostname().split(".")[0].lower()
    if actual!=args.expected_host: raise RuntimeError("REFUSING wrong physical hostname")
    uid_marker="stage9c_t4_"+str(UUID(args.run_id))
    url=os.environ.get("BF4PS_STAGE9C_INTEGRATION_URL","")
    refuse_unsafe_target(url)
    engine=create_engine(url,pool_pre_ping=True,connect_args={"connect_timeout":5,"options":"-c statement_timeout=15000"})
    try:
        with engine.begin() as conn:
            identity=conn.execute(text("""
                SELECT current_database(),current_user,inet_server_addr(),
                       pg_is_in_recovery(),current_setting('transaction_read_only'),
                       current_setting('transaction_isolation')
            """)).one()
            if (identity[0],identity[1],str(identity[2]),identity[3],identity[4],identity[5]) != (
                EXPECTED_DATABASE,EXPECTED_USER,EXPECTED_IP,False,"off","read committed"
            ): raise RuntimeError("REFUSING scratch identity")
            if conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()!="0004_stage9c_supervision_runs":
                raise RuntimeError("REFUSING Alembic head")
            collectors=conn.execute(text("""
                SELECT collector_uuid,hostname FROM collectors
                WHERE collector_name IN (:tcou,:hnl,:kah)
            """),{"tcou":uid_marker+"_tcou","hnl":uid_marker+"_hnl-01","kah":uid_marker+"_kah-01"}).all()
            if len(collectors)!=3 or {c.hostname for c in collectors}!=HOSTS:
                raise RuntimeError("REFUSING incomplete participant registry")
            if len({c.collector_uuid for c in collectors}) != 3:
                raise RuntimeError("REFUSING duplicate collector identity")
            uid=next(c.collector_uuid for c in collectors if c.hostname==actual)
            job=conn.execute(text("""
                SELECT job_id,soldier_id,status,attempt_count FROM collection_jobs
                WHERE reason=:marker
            """),{"marker":uid_marker}).all()
            if len(job)!=1 or job[0].status not in ("pending","claimed") or job[0].attempt_count not in (0,1):
                raise RuntimeError("REFUSING fixture not ready; no reruns")
            if events(conn,uid_marker,RELEASE) or events(conn,uid_marker,DONE):
                raise RuntimeError("REFUSING late participant after release")
            if any(e.host==actual for e in events(conn,uid_marker,READY)):
                raise RuntimeError("REFUSING duplicate host participation")
            emit(conn,uid_marker,READY,host=actual)
        print("READY",actual,flush=True)
        deadline=time.monotonic()+60
        while True:
            with engine.connect() as conn:
                released=events(conn,uid_marker,RELEASE)
                conn.rollback()
            if len(released)==1:
                break
            if released or time.monotonic()>=deadline:
                raise RuntimeError("REFUSING absent/invalid T4 release after bounded wait")
            time.sleep(0.5)
        with engine.begin() as conn:
            if len(events(conn,uid_marker,RELEASE))!=1:
                raise RuntimeError("REFUSING release drift")
            result=claim_production_background_job(
                conn,collector_uuid=uid,resource="detailed",
                allowed_soldier_ids=[job[0].soldier_id],
            )
            if result is not None and result.job_id!=job[0].job_id:
                raise RuntimeError("REFUSING unexpected claimed job")
            emit(conn,uid_marker,DONE,host=actual,
                 outcome=("WIN" if result is not None else "DENIED"))
        print("HOST",actual,"RESULT",("WIN" if result is not None else "DENIED"))
        print("PASS: one bounded scratch claim call, zero HTTP")
    finally:
        engine.dispose()
if __name__=="__main__": main()
