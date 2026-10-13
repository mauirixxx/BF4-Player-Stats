"""Three-node 30-soldier shared-queue bounded collector run."""
import os,sys
from uuid import uuid5,NAMESPACE_DNS
from sqlalchemy import create_engine,text
from bf4ps.collector_runtime import register_collector
from bf4ps.detailed_collector import CollectorIdentity
from scripts.bf4ps_production_collector import collect_one,describe_result
from scripts.phase4c_cohort import PHASE4C_COHORT
from bf4ps.production_hosts import RESOURCES
node=os.uname().nodename.split('.')[0]
assert node in ('tcou','kah-01','hnl-01')
e=create_engine(os.environ['BF4PS_DATABASE_URL'],pool_pre_ping=True)
ps=[p for plat in ('pc','ps4','xboxone') for _,p,_,_ in [r for r in PHASE4C_COHORT if r[3]==plat][:10]]
with e.begin() as c:
 assert c.execute(text('select current_database()')).scalar_one()=='bf4ps_scratch_stage9c_d3'
 ids=[r[0] for r in c.execute(text('select soldier_id from soldiers where persona_id=any(:p)'),{'p':ps}).all()]
 assert len(ids)==30
 ident=CollectorIdentity(uuid5(NAMESPACE_DNS,'four-resource-30-20261012:'+node),'four-resource-30-20261012:'+node,node,'four-resource-30-20261012:'+node,'background')
 register_collector(c,identity=ident,software_version='four-resource-30-smoke')
print('START',node,'soldiers',len(ids),flush=True)
for cycle in range(35):
 any_result=False
 for resource in RESOURCES:
  result=collect_one(e,ident,resource,allowed_soldier_ids=ids,max_total_attempts=30)
  if result is None: continue
  any_result=True
  message,throttle=describe_result(resource,result)
  print(node,message,flush=True)
  if throttle:sys.exit('THROTTLE STOP')
 if not any_result:break
print('DONE',node,flush=True)
