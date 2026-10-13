"""Bounded three-site 1,800-new-soldier soak using proven production primitives."""
import json,os,signal,time
from pathlib import Path
from uuid import uuid5,NAMESPACE_DNS
from sqlalchemy import create_engine,text
from bf4ps.collector_runtime import register_collector,heartbeat_collector,stop_collector
from bf4ps.detailed_collector import CollectorIdentity
from scripts.bf4ps_production_collector import collect_one,describe_result
from bf4ps.production_hosts import RESOURCES
stop=False
def halt(*_):
 global stop
 stop=True
signal.signal(signal.SIGTERM,halt)
signal.signal(signal.SIGINT,halt)
def main():
 host=os.uname().nodename.split('.')[0]
 assert host in ('tcou','kah-01','hnl-01')
 ids=json.loads(Path('/root/bf4ps-1800-soldier-ids.json').read_text())
 assert len(ids)==len(set(ids))==1800
 e=create_engine(os.environ['BF4PS_DATABASE_URL'],pool_pre_ping=True)
 with e.begin() as c:
  assert c.execute(text('select current_database()')).scalar_one()=='bf4ps_scratch_stage9c_d3'
  assert c.execute(text('select count(*) from soldiers where soldier_id = any(:ids)'),{'ids':ids}).scalar_one()==1800
  ident=CollectorIdentity(uuid5(NAMESPACE_DNS,'bf4ps-450-ramp-20261012:'+host),'bf4ps-450-ramp:'+host,host,'bf4ps-450-ramp:'+host,'background')
  register_collector(c,identity=ident,software_version='1800-soak')
 print('START',host,len(ids),flush=True)
 idx=0;last_heartbeat=0;control=None
 try:
  while not stop:
   if time.monotonic()-last_heartbeat>15:
    with e.begin() as c:control=heartbeat_collector(c,collector_uuid=ident.collector_uuid,software_version='1800-soak')
    last_heartbeat=time.monotonic()
   if not control.enabled:break
   if control.drained:time.sleep(1);continue
   resource=RESOURCES[idx%len(RESOURCES)];idx+=1
   result=collect_one(e,ident,resource,allowed_soldier_ids=ids,max_total_attempts=12000)
   if result:
    msg,throttle=describe_result(resource,result);print(host,msg,flush=True)
    if throttle:print('THROTTLE STOP',host,flush=True);break
   else:time.sleep(.3)
 finally:
  with e.begin() as c:stop_collector(c,collector_uuid=ident.collector_uuid)
  e.dispose()
 print('STOP',host,flush=True)
if __name__=='__main__':main()
