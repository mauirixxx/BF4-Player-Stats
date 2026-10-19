"""Import a bounded consistent production cohort into disposable 0013 scratch.

Source transaction is REPEATABLE READ READ ONLY. Scratch is explicitly named and
must be empty. Never connects scratch to a production hostname implicitly.
"""
import argparse
import os
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from bf4ps.ranking_backfill import process_window

p=argparse.ArgumentParser()
p.add_argument('--soldiers',type=int,default=1000)
a=p.parse_args()
if not 1<=a.soldiers<=5000: p.error('cohort size must be 1..5000')
source_url=os.environ['BF4PS_DATABASE_URL']
scratch_url=os.environ['BF4PS_RANKING_SCRATCH_URL']
src=make_url(source_url); dst=make_url(scratch_url)
if src.database!='bf4_playerstats' or dst.database!='bf4ps_ranking_scratch' or dst.host not in ('127.0.0.1','localhost'):
 p.error('REFUSING: production source and local named scratch target required')
if src.host==dst.host and src.port==dst.port: p.error('REFUSING: source and scratch server must differ')
source=create_engine(source_url); target=create_engine(scratch_url)
TABLES={
 'soldiers':'soldier_id persona_id platform current_name first_seen_at last_seen_at created_at updated_at',
 'weapon_catalog':'weapon_id weapon_guid name slug category first_seen_at last_seen_at',
 'vehicle_catalog':'vehicle_id vehicle_guid name slug category first_seen_at last_seen_at',
 'collection_state':'soldier_id weapons_state vehicles_state',
 'soldier_weapon_stats':'soldier_id weapon_id kills headshots shots_fired shots_hit time_equipped_seconds source_fetched_at updated_at',
 'soldier_vehicle_stats':'soldier_id vehicle_id kills time_in_seconds destroy_x_in_y source_fetched_at updated_at',
}
with source.connect() as s, target.begin() as t:
 s.exec_driver_sql('BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
 s.exec_driver_sql("SET LOCAL statement_timeout='120000ms'")
 assert s.execute(text('SELECT current_database()')).scalar_one()=='bf4_playerstats'
 assert t.execute(text('SELECT current_database()')).scalar_one()=='bf4ps_ranking_scratch'
 assert t.execute(text('SELECT version_num FROM alembic_version')).scalar_one()=='0013_indexed_equipment_rankings'
 for table in TABLES:
  if t.execute(text(f'SELECT EXISTS(SELECT 1 FROM {table} LIMIT 1)')).scalar_one():
   raise RuntimeError(f'REFUSING: scratch {table} is not empty')
 snapshot=s.execute(text('SELECT txid_current_snapshot()::text')).scalar_one()
 print('production snapshot:',snapshot,flush=True)
 ids=[r[0] for r in s.execute(text('SELECT soldier_id FROM soldiers ORDER BY soldier_id LIMIT :n'),{'n':a.soldiers})]
 if not ids: raise RuntimeError('no source soldiers')
 for table,fields in TABLES.items():
  columns=fields.split()
  where='' if table.endswith('_catalog') or table=='soldiers' else 'WHERE soldier_id = ANY(:ids)'
  if table=='soldiers': where='WHERE soldier_id = ANY(:ids)'
  q=text(f'SELECT {",".join(columns)} FROM {table} {where}')
  count=0
  cursor=s.execution_options(stream_results=True).execute(q,{'ids':ids})
  ins=text(f'INSERT INTO {table} ({",".join(columns)}) VALUES ({",".join(":"+c for c in columns)})')
  while rows:=cursor.mappings().fetchmany(1000):
   t.execute(ins,[dict(r) for r in rows]); count+=len(rows)
  print('copied',table,count,flush=True)
 for start in range(0,len(ids),200):
  for soldier_id in ids[start:start+200]:
   process_window(t,soldier_id,soldier_id+1)
 print('derived rows:',[(name,t.execute(text(f'SELECT COUNT(*) FROM {name}')).scalar_one()) for name in ('weapon_leaderboard_metrics','vehicle_leaderboard_metrics')],flush=True)
 print('PASS: bounded consistent cohort copied and indexed in scratch',flush=True)
