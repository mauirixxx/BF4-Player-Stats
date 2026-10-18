#!/usr/bin/env python3
"""Single-flight alternating 15-second platoon/soldier scheduler."""
import fcntl
import os
import subprocess
import sys
import time
from pathlib import Path
from platoon_queue_worker import BASE, query

STATE=BASE/'.alternating-next'
LOCK=BASE/'.alternating.lock'
SCRIPTS=Path(__file__).resolve().parent

def due_platoon():
    return query("SELECT EXISTS(SELECT 1 FROM platoon_requests WHERE status IN ('pending','failed') AND next_attempt_at<=now() AND attempts<8) OR EXISTS(SELECT 1 FROM platoons p WHERE COALESCE(p.next_refresh_at,p.last_success_at+interval '1 day',now())<=now() AND NOT EXISTS(SELECT 1 FROM platoon_requests r WHERE r.platoon_id=p.platoon_id AND r.status IN ('pending','failed','running')))")=='t'

def due_soldier():
    return query("SELECT EXISTS(SELECT 1 FROM platoon_soldier_discovery WHERE status IN ('pending','failed') AND next_attempt_at<=now() AND attempts<5)")=='t'

def main():
    BASE.mkdir(parents=True,exist_ok=True)
    with LOCK.open('w') as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            print('Previous operation still running; skip tick',flush=True)
            return 0
        preferred=STATE.read_text().strip() if STATE.exists() else 'platoon'
        if preferred not in ('platoon','soldier'):preferred='platoon'
        platoon=due_platoon();soldier=due_soldier()
        chosen=preferred if (platoon if preferred=='platoon' else soldier) else ('soldier' if soldier else 'platoon' if platoon else None)
        if chosen is None:
            print('No due work',flush=True)
            return 0
        STATE.write_text('soldier' if chosen=='platoon' else 'platoon')
        script='platoon_queue_worker.py' if chosen=='platoon' else 'discover_soldier_platoons.py'
        print('Scheduler selected',chosen,flush=True)
        start=time.monotonic()
        result=subprocess.run([sys.executable,str(SCRIPTS/script)],timeout=210)
        print('Scheduler result',chosen,'exit',result.returncode,'duration_ms',round((time.monotonic()-start)*1000),flush=True)
        return result.returncode

if __name__=='__main__':sys.exit(main())
