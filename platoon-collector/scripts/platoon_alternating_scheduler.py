#!/usr/bin/env python3
"""Single-flight alternating 5-second platoon/soldier scheduler."""
import fcntl
import socket
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
        try:
            result=subprocess.run([sys.executable,str(SCRIPTS/script)],timeout=210,capture_output=True,text=True,errors='replace')
            if result.stdout: print(result.stdout,end='',flush=True)
            if result.stderr: print(result.stderr,end='',file=sys.stderr,flush=True)
            code=result.returncode
            detail=(result.stderr or result.stdout or 'Child process exited nonzero')[-1200:]
        except Exception as exc:
            code=1
            detail=f'{type(exc).__name__}: {exc}'[-1200:]
            print('Scheduler execution failed:',detail,file=sys.stderr,flush=True)
        if code:
            def quoted(v):return "'"+str(v).replace("'","''")+"'"
            try:
                query('INSERT INTO platoon_collector_errors(hostname,work_kind,error_class,error_message) VALUES ('+
                      ','.join(quoted(v) for v in (socket.gethostname(),chosen,'child_failure',detail))+')')
            except Exception as log_exc:
                print('Central error log write failed:',log_exc,file=sys.stderr,flush=True)
        print('Scheduler result',chosen,'exit',code,'duration_ms',round((time.monotonic()-start)*1000),flush=True)
        return code

if __name__=='__main__':sys.exit(main())
