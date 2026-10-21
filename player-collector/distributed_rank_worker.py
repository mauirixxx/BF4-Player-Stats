"""Distributed ranking worker. STAGED: requires migration 0018 and fenced builder.

Set BF4PS_DISTRIBUTED_RANK_ENABLE=1 explicitly; default is to refuse execution.
Production cutover also requires disabling legacy hourly timer and setting
BF4PS_DISTRIBUTED_RANK_REQUIRED=1 on all ranking-builder invocations.
"""
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from bf4ps.distributed_rank_queue import register, discover, claim, renew, finish

HERE = Path(__file__).resolve().parent

def main():
    if os.getenv("BF4PS_DISTRIBUTED_RANK_ENABLE") != "1":
        raise SystemExit("distributed ranking worker disabled by default")
    url = os.environ["BF4PS_DATABASE_URL"]
    database = make_url(url).database
    if database == "bf4_playerstats" and os.getenv("BF4PS_DISTRIBUTED_RANK_REQUIRED") != "1":
        raise SystemExit("production requires BF4PS_DISTRIBUTED_RANK_REQUIRED=1")
    if database not in ("bf4_playerstats", "bf4ps_ranking_scratch"):
        raise SystemExit("unexpected database")
    engine = create_engine(url, pool_pre_ping=True)
    with engine.connect() as c:
        revision = c.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        if revision != "0018_distributed_rank_queue":
            raise SystemExit("migration 0018 required")
    worker = register(engine, socket.gethostname(), os.getenv("BF4PS_SITE"))
    print(f"rank worker registered: {worker}", flush=True)
    last_discovery = 0
    while True:
        if time.monotonic() - last_discovery > 300:
            discover(engine)
            last_discovery = time.monotonic()
        job = claim(engine, worker)
        if job is None:
            with engine.begin() as c:
                c.execute(text("UPDATE equipment_rank_workers SET heartbeat_at=clock_timestamp() WHERE worker_id=:w"), {"w":worker})
            time.sleep(5)
            continue
        cmd = [sys.executable, str(HERE / "build_rank_hourly.py"),
               "--kind", job["kind"], "--item", str(job["item_id"]),
               "--platform", job["platform"], "--metric", job["metric"],
               "--publish", "--rank-worker-id", str(worker),
               "--rank-claim-token", str(job["token"]),
               "--rank-claim-epoch", str(job["epoch"])]
        if database == "bf4_playerstats":
            cmd.append("--production-ack")
        print(f"claimed {job['kind']} {job['item_id']} {job['platform']} {job['metric']}", flush=True)
        process = subprocess.Popen(cmd, env=os.environ.copy())
        lost = False
        while process.poll() is None:
            time.sleep(10)
            try:
                if not renew(engine, job):
                    lost = True
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    break
                with engine.begin() as c:
                    c.execute(text("UPDATE equipment_rank_workers SET heartbeat_at=clock_timestamp() WHERE worker_id=:w"), {"w":worker})
            except Exception:
                lost = True
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                raise
        if lost:
            print("claim lost; builder terminated; refusing completion", flush=True)
            continue
        success = process.returncode == 0
        if not finish(engine, job, success, None if success else f"exit {process.returncode}"):
            print("claim expired before completion; no ownership", flush=True)
        else:
            print(f"completed success={success}", flush=True)

if __name__ == "__main__":
    main()
