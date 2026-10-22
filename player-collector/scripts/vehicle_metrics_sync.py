"""Single-host, rate-limited, resumable reconciliation of vehicle leaderboard metrics.

Runs one vehicle at a time. Saves cursor only after a successful commit.
Environment: BF4PS_DATABASE_URL, BF4PS_SYNC_STATE_DIR (writable mount).
"""
import os
import subprocess
import sys
import time
from pathlib import Path
from sqlalchemy import create_engine, text

state_dir=Path(os.environ.get("BF4PS_SYNC_STATE_DIR","/var/lib/bf4ps-vehicle-sync"))
state_dir.mkdir(parents=True,exist_ok=True)
cursor=state_dir/"last_vehicle_id"
engine=create_engine(os.environ["BF4PS_DATABASE_URL"],pool_pre_ping=True)
delay=max(10,int(os.environ.get("BF4PS_SYNC_INTERVAL_SECONDS","60")))
script=Path(__file__).with_name("repair_vehicle_leaderboard.py")

while True:
    try:
        with engine.connect() as conn:
            vehicle_ids=[r[0] for r in conn.execute(text("SELECT vehicle_id FROM vehicle_catalog ORDER BY vehicle_id"))]
        if not vehicle_ids:
            raise RuntimeError("vehicle catalog empty")
        previous=int(cursor.read_text().strip()) if cursor.exists() else -1
        item=next((v for v in vehicle_ids if v>previous),vehicle_ids[0])
        print(f"reconcile vehicle_id={item}",flush=True)
        result=subprocess.run([sys.executable,str(script),"--vehicle-id",str(item),"--apply"],timeout=180,check=False)
        if result.returncode:
            raise RuntimeError(f"vehicle_id={item} exit={result.returncode}")
        tmp=cursor.with_suffix(".tmp")
        tmp.write_text(str(item)+"\n")
        tmp.replace(cursor)
    except Exception as exc:
        print(f"reconciliation error: {type(exc).__name__}: {exc}",file=sys.stderr,flush=True)
    time.sleep(delay)
