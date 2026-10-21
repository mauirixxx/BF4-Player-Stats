#!/usr/bin/env python3
"""Process at most one due platoon per run; retry failed work with backoff."""
import os,sys,json,time,tempfile,subprocess,urllib.request,uuid,socket
from pathlib import Path

BASE=Path('/var/lib/bf4ps-platoon'); SCRIPTS=Path(__file__).resolve().parent

def query(sql):
 password=Path('/root/.config/bf4ps/platoon-db-password').read_text().strip()
 with tempfile.TemporaryDirectory(prefix='bf4ps-queue-') as tmp:
  pg=Path(tmp)/'pgpass';pg.write_text('db.bf4statusbot.com:5432:bf4_playerstats:bf4ps_platoon_collector:'+password+'\n');pg.chmod(0o600)
  env=dict(os.environ,PGPASSFILE=str(pg),PGSSLMODE='require',PGCONNECT_TIMEOUT='8')
  p=subprocess.run(['psql','-X','-q','-w','-At','-v','ON_ERROR_STOP=1','-h','db.bf4statusbot.com','-U','bf4ps_platoon_collector','-d','bf4_playerstats','-c',sql],capture_output=True,text=True,env=env,timeout=30)
  if p.returncode:raise RuntimeError('Database operation failed: '+p.stderr[-250:])
  return p.stdout.strip()

def main():
 # Single worker enforced by systemd service invocation and timer, plus lock.
 import fcntl
 BASE.mkdir(parents=True,exist_ok=True)
 with (BASE/'.queue.lock').open('w') as lock:
  try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:return 0
  # Fan-in from the eight statistics collectors; only official linked IDs.
  query("""INSERT INTO platoon_requests(platoon_id)
    SELECT DISTINCT d.linked_platoon_id FROM platoon_soldier_discovery d
    WHERE d.status='complete' AND d.linked_platoon_id IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM platoons p WHERE p.platoon_id=d.linked_platoon_id)
    ON CONFLICT DO NOTHING""")
  # Claim and queue transition are ONE SQL statement/transaction.
  # Request and refresh contend on the same platoon_work_leases PK.
  token=str(uuid.uuid4())
  worker=socket.gethostname().replace("'","")
  raw=query(f"""WITH candidate AS (
    SELECT r.platoon_id FROM platoon_requests r
    WHERE ((r.status IN ('pending','failed') AND r.next_attempt_at<=now() AND r.attempts<8)
       OR (r.status='running' AND r.last_attempt_at<now()-interval '15 minutes'))
    ORDER BY r.next_attempt_at,r.platoon_id LIMIT 1 FOR UPDATE OF r SKIP LOCKED
  ), acquired AS (
    INSERT INTO platoon_work_leases(platoon_id,claim_token,claimed_by,lease_until,work_kind)
    SELECT platoon_id,'{token}'::uuid,'{worker}',now()+interval '15 minutes','request' FROM candidate
    ON CONFLICT(platoon_id) DO UPDATE SET
      claim_token=EXCLUDED.claim_token,claimed_by=EXCLUDED.claimed_by,
      lease_until=EXCLUDED.lease_until,claimed_at=now(),work_kind=EXCLUDED.work_kind
    WHERE platoon_work_leases.lease_until<now()
    RETURNING platoon_id,claim_token
  ), claimed AS (
    UPDATE platoon_requests r SET status='running',attempts=r.attempts+1,
      last_attempt_at=now(),next_attempt_at=now()+interval '15 minutes'
    FROM acquired a WHERE r.platoon_id=a.platoon_id
    RETURNING r.platoon_id,a.claim_token
  ) SELECT platoon_id,claim_token FROM claimed""")
  is_new=bool(raw)
  if not raw:
   token=str(uuid.uuid4())
   raw=query(f"""WITH candidate AS (
     SELECT p.platoon_id FROM platoons p
     WHERE COALESCE(p.next_refresh_at,p.last_success_at+interval '1 day',now())<=now()
       AND NOT EXISTS (SELECT 1 FROM platoon_requests r WHERE r.platoon_id=p.platoon_id
                       AND r.status IN ('pending','failed','running'))
     ORDER BY COALESCE(p.next_refresh_at,p.last_success_at+interval '1 day',now()),p.platoon_id
     LIMIT 1 FOR UPDATE OF p SKIP LOCKED
   ), acquired AS (
     INSERT INTO platoon_work_leases(platoon_id,claim_token,claimed_by,lease_until,work_kind)
     SELECT platoon_id,'{token}'::uuid,'{worker}',now()+interval '15 minutes','refresh' FROM candidate
     ON CONFLICT(platoon_id) DO UPDATE SET
       claim_token=EXCLUDED.claim_token,claimed_by=EXCLUDED.claimed_by,
       lease_until=EXCLUDED.lease_until,claimed_at=now(),work_kind=EXCLUDED.work_kind
     WHERE platoon_work_leases.lease_until<now()
     RETURNING platoon_id,claim_token
   ), claimed AS (
     UPDATE platoons p SET next_refresh_at=now()+interval '15 minutes'
     FROM acquired a WHERE p.platoon_id=a.platoon_id
     RETURNING p.platoon_id,a.claim_token
   ) SELECT platoon_id,claim_token FROM claimed""")
  if not raw:
   print('No queued platoons due');return 0
  pid_text,claim_token=raw.splitlines()[0].split('|',1)
  pid=int(pid_text)
  fence=f"platoon_id={pid} AND claim_token='{claim_token}'::uuid AND lease_until>clock_timestamp()"
  print('Claimed',pid,'new',is_new,'token',claim_token,flush=True)
  try:
   with tempfile.TemporaryDirectory(prefix='.queue-',dir=BASE) as tmp:
    html=Path(tmp)/'members.html';roster=Path(tmp)/'roster.json'
    request=urllib.request.Request(f'https://battlelog.battlefield.com/bf4/platoons/members/{pid}/',headers={'User-Agent':'Mozilla/5.0 (compatible; BF4PSPlatoonWatcher/1.0)'})
    with urllib.request.urlopen(request,timeout=35) as response:
     if response.status!=200:raise ValueError('Unexpected HTTP status')
     content=response.read(2_000_001)
     if len(content)>2_000_000:raise ValueError('Oversized response')
    print('HTTP platoon bytes',len(content),'status',response.status,flush=True)
    html.write_bytes(content)
    subprocess.run([sys.executable,str(SCRIPTS/'battlelog_platoon_roster.py'),str(html),'--output',str(roster)],check=True,timeout=30)
    doc=json.loads(roster.read_text())
    if int(doc['platoon']['platoon_id'])!=pid or not doc['validation']['complete']:raise ValueError('Roster validation failed')
    subprocess.run([sys.executable,str(SCRIPTS/'import_platoon_rosters.py'),str(roster),'--claim-token',claim_token],check=True,timeout=120)
    # Soldier bootstrap is ancillary; an excluded identity must never invalidate
    # an otherwise successfully imported, verified platoon roster.
    admission=subprocess.run([sys.executable,str(SCRIPTS/'admit_platoon_soldiers.py')],check=False,timeout=90)
    if admission.returncode:
     print('WARNING soldier bootstrap failed; roster remains valid, exclusion guard enforced',flush=True)
    os.replace(html,BASE/f'{pid}-members.html');os.replace(roster,BASE/f'{pid}-roster.json')
   # Guard + queue finalization + release in one transaction.
   finish=(f"UPDATE platoon_requests SET status='complete',last_error=NULL WHERE platoon_id={pid} AND status='running';"
           if is_new else "")
   query(f"""BEGIN;
     DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM platoon_work_leases WHERE {fence} FOR UPDATE)
       THEN RAISE EXCEPTION 'stale platoon claim'; END IF; END $$;
     {finish}
     UPDATE platoons SET next_refresh_at=now()+interval '1 day' WHERE platoon_id={pid};
     DELETE FROM platoon_work_leases WHERE platoon_id={pid} AND claim_token='{claim_token}'::uuid;
     COMMIT;""")
   print('Completed',pid);return 0
  except Exception as exc:
   message=str(exc).replace("'","''")[:300]
   retry=(f"UPDATE platoon_requests SET status='failed',last_error='{message}',next_attempt_at=now()+interval '1 hour'*LEAST(24,power(2,LEAST(attempts,5))::integer) WHERE platoon_id={pid} AND status='running';"
          if is_new else f"UPDATE platoons SET next_refresh_at=now()+interval '2 hours',last_error='{message}' WHERE platoon_id={pid};")
   try:
    query(f"""BEGIN;
      DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM platoon_work_leases WHERE {fence} FOR UPDATE)
        THEN RAISE EXCEPTION 'stale platoon claim'; END IF; END $$;
      {retry}
      DELETE FROM platoon_work_leases WHERE platoon_id={pid} AND claim_token='{claim_token}'::uuid;
      COMMIT;""")
   except Exception as stale:
    print('Lease no longer owned; not scheduling retry:',stale,file=sys.stderr)
   print('Failed; retry scheduled if still owner:',str(exc),file=sys.stderr);return 1


if __name__=='__main__':sys.exit(main())
