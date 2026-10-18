"""Read production stats only; compare raw and indexed scores in disposable PostgreSQL."""
import os
from sqlalchemy import create_engine,text
source=create_engine(os.environ['BF4PS_DATABASE_URL'])
target=create_engine(os.environ['BF4PS_RANKING_SCRATCH_URL'])
with source.connect() as s,target.begin() as t:
 s.execute(text('SET TRANSACTION READ ONLY'))
 assert s.execute(text('SELECT current_database()')).scalar_one()=='bf4_playerstats'
 assert t.execute(text('SELECT current_database()')).scalar_one()=='bf4ps_ranking_scratch'
 print('revision:',s.execute(text('SELECT version_num FROM alembic_version')).scalar_one(),flush=True)
 for kind,table,item in [('weapon','soldier_weapon_stats',5),('vehicle','soldier_vehicle_stats',1)]:
  fields='kills,time_equipped_seconds,shots_fired,shots_hit' if kind=='weapon' else 'kills,time_in_seconds'
  t.execute(text(f'CREATE TABLE {kind}_raw (soldier_id bigint PRIMARY KEY,{", ".join(x+" bigint" for x in fields.split(","))})'))
  q=f'SELECT soldier_id,{fields} FROM {table} WHERE {kind}_id=:item'
  cursor=s.execution_options(stream_results=True).execute(text(q),{'item':item})
  ins=text(f'INSERT INTO {kind}_raw(soldier_id,{fields}) VALUES (:soldier_id,{",".join(":"+x for x in fields.split(","))})')
  count=0
  while batch:=cursor.mappings().fetchmany(2000):
   t.execute(ins,[dict(row) for row in batch]);count+=len(batch)
  print(kind,'real rows copied:',count,flush=True)
  if kind=='weapon':
   computed='CASE WHEN time_equipped_seconds>=60 THEN kills::numeric*60/time_equipped_seconds END kpm, CASE WHEN shots_fired>=100 AND shots_hit<=shots_fired THEN shots_hit::numeric*100/shots_fired END accuracy'
  else:computed='CASE WHEN time_in_seconds>=60 THEN kills::numeric*60/time_in_seconds END kpm'
  t.execute(text(f'CREATE TABLE {kind}_rank AS SELECT soldier_id,kills,{computed} FROM {kind}_raw'))
  for metric in (['kills','kpm','accuracy'] if kind=='weapon' else ['kills','kpm']):
   t.execute(text(f'CREATE INDEX ON {kind}_rank ({metric} DESC NULLS LAST,soldier_id)'))
  t.execute(text(f'ANALYZE {kind}_raw'));t.execute(text(f'ANALYZE {kind}_rank'))
with target.connect() as c:
 c.execute(text('SET TRANSACTION READ ONLY'))
 for kind in ['weapon','vehicle']:
  for metric in (['kills','kpm','accuracy'] if kind=='weapon' else ['kills','kpm']):
   if metric=='kills':expr='kills';condition='TRUE'
   elif metric=='accuracy':expr='shots_hit::numeric*100/NULLIF(shots_fired,0)';condition='shots_fired>=100 AND shots_hit<=shots_fired'
   else:expr='kills::numeric*60/NULLIF('+('time_equipped_seconds' if kind=='weapon' else 'time_in_seconds')+',0)';condition=('time_equipped_seconds' if kind=='weapon' else 'time_in_seconds')+'>=60'
   a=f'SELECT soldier_id,{expr} score FROM {kind}_raw WHERE {condition} ORDER BY score DESC NULLS LAST,soldier_id LIMIT 10'
   b=f'SELECT soldier_id,{metric} score FROM {kind}_rank WHERE {metric} IS NOT NULL ORDER BY {metric} DESC NULLS LAST,soldier_id LIMIT 10'
   assert c.execute(text(a)).all()==c.execute(text(b)).all(),(kind,metric)
   print('PARITY PASS',kind,metric,flush=True)
   for name,q in [('raw',a),('indexed',b)]:
    plan=c.execute(text('EXPLAIN (ANALYZE,BUFFERS) '+q)).scalars().all()
    print('BENCH',kind,metric,name,next(line for line in plan if line.startswith('Execution Time:')),flush=True)
