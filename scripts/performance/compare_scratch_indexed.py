"""Compare actual populated 0013 read models with independently recomputed raw data."""
import os
from sqlalchemy import create_engine,text
from sqlalchemy.engine import make_url
from bf4ps.ranking_backfill import vehicle_family_sql,vehicle_mode_sql
url=os.environ['BF4PS_DATABASE_URL']; u=make_url(url)
assert u.database=='bf4ps_ranking_scratch' and u.host in ('localhost','127.0.0.1')
e=create_engine(url)
with e.connect() as c:
 c.execute(text('BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
 c.execute(text("SET LOCAL statement_timeout='120000ms'"))
 assert c.execute(text('SELECT version_num FROM alembic_version')).scalar_one()=='0013_indexed_equipment_rankings'
 weapon='''SELECT w.soldier_id,w.weapon_id,MAX(w.kills) kills,CASE WHEN MAX(w.time_equipped_seconds)>=60 THEN MAX(w.kills)::numeric*60/MAX(w.time_equipped_seconds) END kpm,CASE WHEN MAX(w.shots_fired)>=100 AND MAX(w.shots_hit)<=MAX(w.shots_fired) THEN MAX(w.shots_hit)::numeric*100/MAX(w.shots_fired) END accuracy,MAX(w.source_fetched_at) source_fetched_at FROM soldier_weapon_stats w JOIN collection_state cs ON cs.soldier_id=w.soldier_id WHERE cs.weapons_state='success' GROUP BY w.soldier_id,w.weapon_id'''
 vehicle=f'''WITH raw AS (SELECT v.soldier_id,{vehicle_family_sql()} family_id,{vehicle_mode_sql()} mode,MAX(v.kills) kills,MAX(v.time_in_seconds) seconds,MAX(v.source_fetched_at) fetched FROM soldier_vehicle_stats v JOIN collection_state cs ON cs.soldier_id=v.soldier_id WHERE cs.vehicles_state='success' GROUP BY v.soldier_id,v.vehicle_id), family AS (SELECT soldier_id,family_id,CASE WHEN MAX(mode)='sum' THEN SUM(kills) ELSE MAX(kills) END kills,CASE WHEN MAX(mode)='sum' THEN SUM(seconds) ELSE MAX(seconds) END seconds,MAX(fetched) fetched FROM raw GROUP BY soldier_id,family_id) SELECT soldier_id,family_id vehicle_id,kills,CASE WHEN seconds>=60 THEN kills::numeric*60/seconds END kpm,fetched source_fetched_at FROM family'''
 for kind,raw,table in [('weapon',weapon,'weapon_leaderboard_metrics'),('vehicle',vehicle,'vehicle_leaderboard_metrics')]:
  cols='soldier_id,weapon_id,kills,kpm,accuracy,source_fetched_at' if kind=='weapon' else 'soldier_id,vehicle_id,kills,kpm,source_fetched_at'
  q=f'''WITH expected AS ({raw}), actual AS (SELECT {cols} FROM {table}), differences AS ((SELECT * FROM expected EXCEPT ALL SELECT * FROM actual) UNION ALL (SELECT * FROM actual EXCEPT ALL SELECT * FROM expected)) SELECT (SELECT count(*) FROM expected) expected_count,(SELECT count(*) FROM actual) actual_count,(SELECT count(*) FROM differences) mismatches'''
  result=c.execute(text(q)).one()
  print('FULL',kind,dict(result._mapping),flush=True)
  assert result.expected_count==result.actual_count and result.mismatches==0,(kind,result)
  for item in (5,6) if kind=='weapon' else (1,2,41,62):
   for platform in ('all','pc'):
    for metric in ('kills','kpm','accuracy') if kind=='weapon' else ('kills','kpm'):
     filt='' if platform=='all' else "AND s.platform='pc'"
     # The website-managed player_exclusions table is not in Alembic 0013 scratch.
     # Exclusion parity needs a separately imported exclusion snapshot.
     exclusion='TRUE'
     def query(data):
      return f'''WITH cohort AS (SELECT d.soldier_id,d.{metric} score FROM ({data}) d JOIN soldiers s ON s.soldier_id=d.soldier_id WHERE d.{kind}_id=:item AND {exclusion} {filt}), ranked AS (SELECT soldier_id,score,rank() OVER (ORDER BY score DESC NULLS LAST) rank,row_number() OVER(ORDER BY score DESC NULLS LAST,soldier_id) position,count(*) OVER() population FROM cohort), output AS (SELECT *,rank*100.0/NULLIF(population,0) top_pct,CASE WHEN rank*100.0/NULLIF(population,0)<=3 THEN 1 WHEN rank*100.0/NULLIF(population,0)<=8 THEN 2 WHEN rank*100.0/NULLIF(population,0)<=15 THEN 3 WHEN rank*100.0/NULLIF(population,0)<=25 THEN 4 WHEN rank*100.0/NULLIF(population,0)<=35 THEN 5 WHEN rank*100.0/NULLIF(population,0)<=50 THEN 6 WHEN rank*100.0/NULLIF(population,0)<=65 THEN 7 WHEN rank*100.0/NULLIF(population,0)<=80 THEN 8 WHEN rank*100.0/NULLIF(population,0)<=90 THEN 9 ELSE 10 END division FROM ranked) SELECT * FROM output'''
     a=query(raw); b=query(f'SELECT {cols} FROM {table}')
     compare=f'''WITH old AS ({a}), new AS ({b}), diff AS ((SELECT * FROM old EXCEPT ALL SELECT * FROM new) UNION ALL (SELECT * FROM new EXCEPT ALL SELECT * FROM old)) SELECT (SELECT count(*) FROM old) population,(SELECT count(*) FROM diff) mismatches'''
     result=c.execute(text(compare),{'item':item}).one()
     print('RANK',kind,item,platform,metric,'population',result.population,'mismatches',result.mismatches,flush=True)
     assert result.mismatches==0,(kind,item,platform,metric,result)
 print('PASS: complete raw-vs-indexed record and ranking parity',flush=True)
