"""Exercise actual generated scheduler claim SQL against disposable PostgreSQL."""
import importlib.util,subprocess,tempfile,pathlib,time
root=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("worker",root/"scripts/platoon_queue_worker.py")
worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)
queries=[]
with tempfile.TemporaryDirectory() as tmp:
 worker.BASE=pathlib.Path(tmp)
 def fake_query(q):
  queries.append(q)
  return ""
 worker.query=fake_query
 assert worker.main()==0
assert len(queries)==3,len(queries)
def sql(q):
 p=subprocess.run(["docker","exec","-i","bf4ps-claim-sql-check","psql","-X","-q","-At","-v","ON_ERROR_STOP=1","-U","postgres","-d","postgres"],input=q,text=True,capture_output=True,timeout=15)
 if p.returncode:raise RuntimeError(p.stderr+"\n"+q)
 return p.stdout.strip()
for _ in range(40):
 try:sql("SELECT 1");break
 except RuntimeError:time.sleep(.25)
sql("""CREATE TABLE platoon_requests(platoon_id bigint PRIMARY KEY,status text,attempts integer DEFAULT 0,next_attempt_at timestamptz DEFAULT now(),last_attempt_at timestamptz);
CREATE TABLE platoons(platoon_id bigint PRIMARY KEY,next_refresh_at timestamptz,last_success_at timestamptz);
CREATE TABLE platoon_work_leases(platoon_id bigint PRIMARY KEY,claim_token uuid NOT NULL,claimed_by text NOT NULL,lease_until timestamptz NOT NULL,claimed_at timestamptz DEFAULT now(),work_kind text);
INSERT INTO platoon_requests(platoon_id,status) VALUES(101,'pending');
INSERT INTO platoons(platoon_id,next_refresh_at) VALUES(102,now()-interval '1 day');""")
req=sql(queries[1]);ref=sql(queries[2])
assert req.startswith("101|"),req
assert ref.startswith("102|"),ref
assert sql(queries[1])=="" 
assert sql(queries[2])==""
assert sql("SELECT count(*) FROM platoon_work_leases")=="2"
print("PASS actual request SQL claims 101")
print("PASS actual refresh SQL claims 102")
print("PASS repeated claims blocked by shared lease")
