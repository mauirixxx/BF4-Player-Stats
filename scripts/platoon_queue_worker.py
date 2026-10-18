#!/usr/bin/env python3
"""Process at most one due platoon per run; retry failed work with backoff."""
import os,sys,json,time,tempfile,subprocess,urllib.request
from pathlib import Path

BASE=Path('/var/lib/bf4ps-platoon'); SCRIPTS=Path(__file__).resolve().parent

def query(sql):
 password=Path('/root/.config/bf4ps/platoon-db-password').read_text().strip()
 with tempfile.TemporaryDirectory(prefix='bf4ps-queue-') as tmp:
  pg=Path(tmp)/'pgpass';pg.write_text('db.bf4statusbot.com:5432:bf4_playerstats:bf4ps_platoon_collector:'+password+'\n');pg.chmod(0o600)
  env=dict(os.environ,PGPASSFILE=str(pg),PGSSLMODE='require',PGCONNECT_TIMEOUT='8')
  p=subprocess.run(['psql','-X','-w','-At','-v','ON_ERROR_STOP=1','-h','db.bf4statusbot.com','-U','bf4ps_platoon_collector','-d','bf4_playerstats','-c',sql],capture_output=True,text=True,env=env,timeout=30)
  if p.returncode:raise RuntimeError('Database operation failed: '+p.stderr[-250:])
  return p.stdout.strip()

def main():
 # Single worker enforced by systemd service invocation and timer, plus lock.
 import fcntl
 BASE.mkdir(parents=True,exist_ok=True)
 with (BASE/'.queue.lock').open('w') as lock:
  try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:return 0
  raw=query("SELECT platoon_id FROM platoon_requests WHERE status IN ('pending','failed') AND next_attempt_at<=now() AND attempts<8 ORDER BY next_attempt_at,requested_at LIMIT 1")
  if not raw:
   print('No queued platoons due');return 0
  pid=int(raw.splitlines()[0]);print('Processing',pid,flush=True)
  query(f"UPDATE platoon_requests SET status='running',attempts=attempts+1,last_attempt_at=now() WHERE platoon_id={pid}")
  try:
   with tempfile.TemporaryDirectory(prefix='.queue-',dir=BASE) as tmp:
    html=Path(tmp)/'members.html';roster=Path(tmp)/'roster.json'
    request=urllib.request.Request(f'https://battlelog.battlefield.com/bf4/platoons/members/{pid}/',headers={'User-Agent':'Mozilla/5.0 (compatible; BF4PSPlatoonWatcher/1.0)'})
    with urllib.request.urlopen(request,timeout=35) as response:
     if response.status!=200:raise ValueError('Unexpected HTTP status')
     content=response.read(2_000_001)
     if len(content)>2_000_000:raise ValueError('Oversized response')
    html.write_bytes(content)
    subprocess.run([sys.executable,str(SCRIPTS/'battlelog_platoon_roster.py'),str(html),'--output',str(roster)],check=True,timeout=30)
    doc=json.loads(roster.read_text())
    if int(doc['platoon']['platoon_id'])!=pid or not doc['validation']['complete']:raise ValueError('Roster validation failed')
    subprocess.run([sys.executable,str(SCRIPTS/'import_platoon_rosters.py'),str(roster)],check=True,timeout=120)
    os.replace(html,BASE/f'{pid}-members.html');os.replace(roster,BASE/f'{pid}-roster.json')
   query(f"UPDATE platoon_requests SET status='complete',last_error=NULL WHERE platoon_id={pid}")
   print('Completed',pid);return 0
  except Exception as exc:
   message=str(exc).replace("'","''")[:300]
   query(f"UPDATE platoon_requests SET status='failed',last_error='{message}',next_attempt_at=now()+interval '1 hour'*LEAST(24,power(2,LEAST(attempts,5))::integer) WHERE platoon_id={pid}")
   print('Failed; retry scheduled:',str(exc),file=sys.stderr);return 1

if __name__=='__main__':sys.exit(main())
