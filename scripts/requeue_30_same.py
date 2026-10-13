"""Requeue exactly the original 30-persona cohort; preserve existing collected rows/events."""
import os
from sqlalchemy import create_engine,text
from bf4ps.collection_jobs import enqueue_job
from scripts.phase4c_cohort import PHASE4C_COHORT
ps=[p for plat in ('pc','ps4','xboxone') for _,p,_,_ in [r for r in PHASE4C_COHORT if r[3]==plat][:10]]
e=create_engine(os.environ['BF4PS_DATABASE_URL'])
with e.begin() as c:
 assert c.execute(text('select current_database()')).scalar_one()=='bf4ps_scratch_stage9c_d3'
 ids=[int(r[0]) for r in c.execute(text('select soldier_id from soldiers where persona_id=any(:p)'),{'p':ps}).all()]
 assert len(ids)==30
 for sid in ids:
  for resource in ('detailed','weapons','vehicles','profile'):
   existing=c.execute(text('select job_id,status from collection_jobs where soldier_id=:sid and resource=:r'),{'sid':sid,'r':resource}).first()
   if existing:
    c.execute(text("""update collection_jobs set status='pending',eligible_at=now(),
      collector_uuid=null,lease_token=null,claimed_at=null,started_at=null,
      lease_expires_at=null,last_error_at=null,last_error_class=null,updated_at=now()
      where soldier_id=:sid and resource=:r"""),{'sid':sid,'r':resource})
   else:
    enqueue_job(c,soldier_id=sid,resource=resource,reason='four-resource-30-20261012-rerun',priority_class='bootstrap',priority_value=100000)
 total=c.execute(text('select count(*) from collection_jobs where soldier_id=any(:ids)'),{'ids':ids}).scalar_one()
 assert total==120,total
 print('REQUEUED 120 jobs across same 30 soldiers; historical data/events retained',flush=True)
