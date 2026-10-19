"""Real collector success handler, lease fencing and same-soldier lock stress, scratch only."""
import os
from datetime import datetime,timezone
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from sqlalchemy import create_engine,text
from sqlalchemy.engine import make_url
from bf4ps.collection_jobs import ClaimedJob
from bf4ps.battlelog_weapons import NormalizedWeaponStat
from bf4ps.battlelog_vehicles import NormalizedVehicleStat
from bf4ps.weapon_persistence import persist_weapon_success
from bf4ps.vehicle_persistence import persist_vehicle_success
from bf4ps.ranking_backfill import refresh_soldier_metrics
u=make_url(os.environ['BF4PS_DATABASE_URL'])
assert u.database=='bf4ps_ranking_scratch' and u.host in ('127.0.0.1','localhost')
os.environ['BF4PS_RANKING_DERIVED_WRITES']='1'
e=create_engine(os.environ['BF4PS_DATABASE_URL'],pool_size=4,max_overflow=0)
with e.connect() as c:
 assert c.execute(text('SELECT version_num FROM alembic_version')).scalar_one()=='0013_indexed_equipment_rankings'
 soldier=c.execute(text('SELECT soldier_id,persona_id,platform FROM soldiers WHERE soldier_id IN (SELECT soldier_id FROM weapon_leaderboard_metrics) ORDER BY soldier_id LIMIT 1')).one()
 wid=c.execute(text('SELECT weapon_guid,name,slug,category FROM weapon_catalog WHERE weapon_id=5')).one()
 vid=c.execute(text('SELECT vehicle_guid,name,slug,category FROM vehicle_catalog WHERE vehicle_id=1')).one()
 print('scratch soldier',soldier.soldier_id,flush=True)

def job_for(c,resource):
 uid=uuid4(); lease=uuid4()
 c.execute(text("INSERT INTO collectors(collector_uuid,collector_name,hostname,lane,egress_key) VALUES (:id,:name,'scratch','background','scratch')"),{'id':uid,'name':str(uid)})
 jid=c.execute(text("INSERT INTO collection_jobs(soldier_id,resource,lane,priority_class,reason,status,attempt_count,collector_uuid,lease_token,claimed_at,started_at,lease_expires_at) VALUES (:s,:r,'background','bootstrap','scratch-test','running',1,:id,:lease,now(),now(),now()+interval '5 minutes') RETURNING job_id"),{'s':soldier.soldier_id,'r':resource,'id':uid,'lease':lease}).scalar_one()
 return ClaimedJob(jid,soldier.soldier_id,resource,'background',1,uid,lease)

def persist(c,job):
 common=dict(conn=c,job=job,source_fetched_at=datetime.now(timezone.utc),persona_id=soldier.persona_id,platform=soldier.platform,collector_name='scratch-test',hostname='scratch',egress_key='scratch',duration_ms=10,response_bytes=100)
 if job.resource=='weapons':
  return persist_weapon_success(**common,weapons=[NormalizedWeaponStat(wid.weapon_guid,wid.name,wid.slug,wid.category,8888,5,300,120,300)])
 return persist_vehicle_success(**common,vehicles=[NormalizedVehicleStat(vid.vehicle_guid,vid.name,vid.slug,vid.category,7777,300,None)])

# Complete real persistence including lease check, raw replacement, derived refresh,
# collection event, and job finalization. Transaction rolled back after assertions.
for resource,table,item in [('weapons','weapon_leaderboard_metrics',5),('vehicles','vehicle_leaderboard_metrics',1)]:
 with e.connect() as c:
  tx=c.begin()
  try:
   j=job_for(c,resource)
   stale=ClaimedJob(j.job_id,j.soldier_id,j.resource,j.lane,j.attempt_count,j.collector_uuid,uuid4())
   try: persist(c,stale)
   except RuntimeError as exc: assert 'lease' in str(exc)
   else: raise AssertionError('stale lease accepted')
   assert persist(c,j)==1
   assert c.execute(text(f'SELECT kills FROM {table} WHERE soldier_id=:s AND {"weapon_id" if resource=="weapons" else "vehicle_id"}=:i'),{'s':soldier.soldier_id,'i':item}).scalar_one()==(8888 if resource=='weapons' else 7777)
   assert c.execute(text('SELECT COUNT(*) FROM collection_events WHERE job_id=:j AND event_type=\'collection_success\''),{'j':j.job_id}).scalar_one()==1
   assert c.execute(text('SELECT COUNT(*) FROM collection_jobs WHERE job_id=:j'),{'j':j.job_id}).scalar_one()==0
   print('PASS: full',resource,'collector handler; stale lease rejected, event and finalization verified',flush=True)
  finally: tx.rollback()

# Simultaneous same-soldier refreshes, using database advisory locks to model
# serialized collector ownership, and an explicit lock timeout to detect contention.
barrier=Barrier(2)
def contend(i):
 with e.connect() as c:
  tx=c.begin()
  try:
   c.execute(text("SET LOCAL lock_timeout='10000ms'"))
   barrier.wait(timeout=10)
   c.execute(text('SELECT soldier_id FROM soldiers WHERE soldier_id=:s FOR UPDATE'),{'s':soldier.soldier_id})
   refresh_soldier_metrics(c,soldier.soldier_id,'weapons')
   refresh_soldier_metrics(c,soldier.soldier_id,'vehicles')
   return i
  finally: tx.rollback()
with ThreadPoolExecutor(max_workers=2) as pool:
 results=list(pool.map(contend,[1,2]))
assert results==[1,2]
print('PASS: two simultaneous same-soldier transactions serialize successfully under row lock',flush=True)
print('PASS: collector integration and same-soldier concurrency suite',flush=True)
