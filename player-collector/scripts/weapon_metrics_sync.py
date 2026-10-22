"""Single-host, rate-limited, resumable reconciliation of weapon leaderboard metrics.

Runs one weapon at a time. Saves cursor only after a successful commit.
Environment: BF4PS_DATABASE_URL, BF4PS_SYNC_STATE_DIR (writable mount).
"""
import os
import subprocess
import sys
import time
from pathlib import Path
from sqlalchemy import create_engine, text

state_dir=Path(os.environ.get("BF4PS_SYNC_STATE_DIR","/var/lib/bf4ps-weapon-sync"))
state_dir.mkdir(parents=True,exist_ok=True)
cursor=state_dir/"last_weapon_id"
engine=create_engine(os.environ["BF4PS_DATABASE_URL"],pool_pre_ping=True)
delay=max(10,int(os.environ.get("BF4PS_SYNC_INTERVAL_SECONDS","60")))
script=Path(__file__).with_name("repair_weapon_leaderboard.py")

while True:
    try:
        with engine.connect() as conn:
            weapon_ids=[r[0] for r in conn.execute(text("SELECT weapon_id FROM weapon_catalog ORDER BY weapon_id"))]
        if not weapon_ids:
            raise RuntimeError("weapon catalog empty")
        previous=int(cursor.read_text().strip()) if cursor.exists() else -1
        item=next((v for v in weapon_ids if v>previous),weapon_ids[0])
        print(f"reconcile weapon_id={item}",flush=True)
        result=subprocess.run([sys.executable,str(script),"--weapon-id",str(item),"--apply"],timeout=180,check=False)
        if result.returncode:
            raise RuntimeError(f"weapon_id={item} exit={result.returncode}")
        tmp=cursor.with_suffix(".tmp")
        tmp.write_text(str(item)+"\n")
        tmp.replace(cursor)
    except Exception as exc:
        print(f"reconciliation error: {type(exc).__name__}: {exc}",file=sys.stderr,flush=True)
    time.sleep(delay)
