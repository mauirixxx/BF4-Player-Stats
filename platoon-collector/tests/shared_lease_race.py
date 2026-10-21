"""Isolated PostgreSQL test for shared request/refresh claim ownership."""
import subprocess,threading,uuid
C="bf4ps-platoon-shared-lease-test"
def run(*args,input=None):
 p=subprocess.run(args,input=input,text=True,capture_output=True,timeout=30)
 if p.returncode:raise RuntimeError(p.stderr)
 return p.stdout.strip()
def sql(s):
 return run("docker","exec","-i",C,"psql","-X","-q","-A","-t","-v","ON_ERROR_STOP=1","-U","postgres","-d","postgres",input=s)
run("docker","run","-d","--name",C,"--network","none","-e","POSTGRES_PASSWORD=isolated-only","postgres:16-alpine")
try:
 import time
 for _ in range(100):
  try:
   sql("SELECT 1");break
  except RuntimeError:time.sleep(.5)
 sql("""CREATE TABLE platoon_work_leases(platoon_id bigint PRIMARY KEY,claim_token uuid NOT NULL,claimed_by text NOT NULL,lease_until timestamptz NOT NULL,claimed_at timestamptz NOT NULL DEFAULT now(),work_kind text NOT NULL CHECK(work_kind IN ('request','refresh')));
 CREATE TABLE roster(platoon_id bigint PRIMARY KEY,name text);
 INSERT INTO roster VALUES(42,'original');""")
 def claim(kind):
  token=str(uuid.uuid4())
  result=sql(f"""INSERT INTO platoon_work_leases(platoon_id,claim_token,claimed_by,lease_until,work_kind)
 VALUES(42,'{token}','test-{kind}',now()+interval '15 minutes','{kind}')
 ON CONFLICT(platoon_id) DO UPDATE SET claim_token=EXCLUDED.claim_token,claimed_by=EXCLUDED.claimed_by,lease_until=EXCLUDED.lease_until,claimed_at=now(),work_kind=EXCLUDED.work_kind
 WHERE platoon_work_leases.lease_until<now() RETURNING claim_token;""")
  return token,result
 barrier=threading.Barrier(3);results=[]
 def worker(kind):
  barrier.wait();results.append((kind,claim(kind)))
 threads=[threading.Thread(target=worker,args=(k,)) for k in ("request","refresh")]
 for t in threads:t.start()
 barrier.wait()
 for t in threads:t.join()
 winners=[(k,v[0]) for k,v in results if v[1]]
 assert len(winners)==1,results
 winner=winners[0][1]
 print("PASS: request and refresh race -> exactly one shared claim")
 assert sql("SELECT count(*) FROM platoon_work_leases WHERE platoon_id=42")=="1"
 sql("UPDATE platoon_work_leases SET lease_until=now()-interval '1 second' WHERE platoon_id=42")
 new_token,result=claim("refresh")
 assert result==new_token and new_token!=winner
 print("PASS: expired shared claim reclaimed")
 # Match importer transaction guard: stale token must raise and abort before writing.
 stale=sql(f"""BEGIN;
 DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM platoon_work_leases WHERE platoon_id=42 AND claim_token='{winner}'::uuid AND lease_until>clock_timestamp() FOR UPDATE) THEN RAISE EXCEPTION 'stale claim'; END IF; END $$;
 UPDATE roster SET name='stale' WHERE platoon_id=42;
 COMMIT;""") if False else None
 p=subprocess.run(["docker","exec","-i",C,"psql","-X","-v","ON_ERROR_STOP=1","-U","postgres","-d","postgres"],input=f"""BEGIN;
 DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM platoon_work_leases WHERE platoon_id=42 AND claim_token='{winner}'::uuid AND lease_until>clock_timestamp() FOR UPDATE) THEN RAISE EXCEPTION 'stale claim'; END IF; END $$;
 UPDATE roster SET name='stale' WHERE platoon_id=42;
 COMMIT;""",text=True,capture_output=True,timeout=20)
 assert p.returncode!=0 and "stale claim" in p.stderr
 assert sql("SELECT name FROM roster WHERE platoon_id=42")=="original"
 print("PASS: stale worker import rejected with no writes")
 sql(f"""BEGIN;
 DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM platoon_work_leases WHERE platoon_id=42 AND claim_token='{new_token}'::uuid AND lease_until>clock_timestamp() FOR UPDATE) THEN RAISE EXCEPTION 'stale claim'; END IF; END $$;
 UPDATE roster SET name='current' WHERE platoon_id=42;
 COMMIT;""")
 assert sql("SELECT name FROM roster WHERE platoon_id=42")=="current"
 print("PASS: current owner import committed")
finally:
 run("docker","rm","-f",C)
