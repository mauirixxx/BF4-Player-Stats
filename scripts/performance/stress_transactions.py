"""Scratch-only live derived-refresh concurrency, rollback and exclusions tests."""
import os
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import create_engine,text
from sqlalchemy.engine import make_url
from bf4ps.ranking_backfill import refresh_soldier_metrics
u=make_url(os.environ['BF4PS_DATABASE_URL'])
assert u.database=='bf4ps_ranking_scratch' and u.host in ('localhost','127.0.0.1')
e=create_engine(os.environ['BF4PS_DATABASE_URL'],pool_size=8,max_overflow=0)
with e.connect() as c:
 assert c.execute(text('SELECT version_num FROM alembic_version')).scalar_one()=='0013_indexed_equipment_rankings'
 ids=[r[0] for r in c.execute(text('SELECT soldier_id FROM weapon_leaderboard_metrics GROUP BY soldier_id ORDER BY soldier_id LIMIT 32'))]
 assert len(ids)==32
 soldier=ids[0]
 original=c.execute(text('SELECT weapon_id,kills FROM weapon_leaderboard_metrics WHERE soldier_id=:s ORDER BY weapon_id LIMIT 1'),{'s':soldier}).one()
 print('baseline soldier',soldier,'weapon',original.weapon_id,'kills',original.kills,flush=True)
# A forced exception must roll back raw rows AND derived rows atomically.
try:
 with e.begin() as c:
  c.execute(text('UPDATE soldier_weapon_stats SET kills=kills+99 WHERE soldier_id=:s AND weapon_id=:w'),{'s':soldier,'w':original.weapon_id})
  refresh_soldier_metrics(c,soldier,'weapons')
  assert c.execute(text('SELECT kills FROM weapon_leaderboard_metrics WHERE soldier_id=:s AND weapon_id=:w'),{'s':soldier,'w':original.weapon_id}).scalar_one()==original.kills+99
  raise RuntimeError('intentional transaction failure')
except RuntimeError: pass
with e.connect() as c:
 assert c.execute(text('SELECT kills FROM soldier_weapon_stats WHERE soldier_id=:s AND weapon_id=:w'),{'s':soldier,'w':original.weapon_id}).scalar_one()==original.kills
 assert c.execute(text('SELECT kills FROM weapon_leaderboard_metrics WHERE soldier_id=:s AND weapon_id=:w'),{'s':soldier,'w':original.weapon_id}).scalar_one()==original.kills
print('PASS: full transaction rollback restores raw and derived rows',flush=True)
# Repeated concurrent transactions on distinct soldiers; roll back each so scratch baseline stays intact.
def worker(item):
 with e.connect() as c:
  trans=c.begin()
  try:
   c.execute(text("SET LOCAL statement_timeout='30000ms'"))
   for resource in ('weapons','vehicles'):
    refresh_soldier_metrics(c,item,resource)
   n=c.execute(text('SELECT COUNT(*) FROM weapon_leaderboard_metrics WHERE soldier_id=:s'),{'s':item}).scalar_one()
   return n
  finally: trans.rollback()
with ThreadPoolExecutor(max_workers=8) as pool:
 result=list(pool.map(worker,ids*3))
assert all(x>0 for x in result)
print('PASS: 96 concurrent resource refresh transactions across 8 workers, all rolled back',flush=True)
# Exclusions are website-owned, not part of Alembic. Use an isolated TEMP table
# and assert that the same active exclusion removes exactly the same identities
# from raw and indexed cohorts, without modifying either underlying table.
with e.begin() as c:
 c.execute(text('CREATE TEMP TABLE player_exclusions (platform text,persona_id bigint,active boolean) ON COMMIT DROP'))
 row=c.execute(text('SELECT platform,persona_id FROM soldiers WHERE soldier_id=:s'),{'s':soldier}).one()
 c.execute(text('INSERT INTO player_exclusions VALUES (:p,:id,true)'),{'p':row.platform,'id':row.persona_id})
 predicate='NOT EXISTS(SELECT 1 FROM player_exclusions pe WHERE pe.platform=s.platform AND pe.persona_id=s.persona_id AND pe.active)'
 for table,raw,state in [('weapon_leaderboard_metrics','soldier_weapon_stats','weapons'),('vehicle_leaderboard_metrics','soldier_vehicle_stats','vehicles')]:
  for excluded in (False,True):
   where=predicate if excluded else 'TRUE'
   a=c.execute(text(f"SELECT count(DISTINCT r.soldier_id) FROM {raw} r JOIN soldiers s ON s.soldier_id=r.soldier_id JOIN collection_state cs ON cs.soldier_id=s.soldier_id WHERE cs.{state}_state='success' AND {where}")).scalar_one()
   b=c.execute(text(f'SELECT count(DISTINCT d.soldier_id) FROM {table} d JOIN soldiers s ON s.soldier_id=d.soldier_id WHERE {where}')).scalar_one()
   assert a==b,(table,excluded,a,b)
  c.execute(text('UPDATE player_exclusions SET active=false'))
  assert c.execute(text(f'SELECT count(*) FROM {table} d JOIN soldiers s ON s.soldier_id=d.soldier_id WHERE {predicate}')).scalar_one()==c.execute(text(f'SELECT count(*) FROM {table}')).scalar_one()
  c.execute(text('UPDATE player_exclusions SET active=true'))
 print('PASS: active/inactive website-style exclusions agree on raw and indexed soldier eligibility',flush=True)
print('PASS: scratch transactional/concurrency/exclusion suite',flush=True)
