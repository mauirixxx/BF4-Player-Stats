"""Scratch-only deterministic parity and restart test for ranking backfill."""
import os
from decimal import Decimal
from sqlalchemy import create_engine,text
from sqlalchemy.engine import make_url
from bf4ps.ranking_backfill import process_window

url=os.environ['BF4PS_DATABASE_URL']; parsed=make_url(url)
assert parsed.database=='bf4ps_ranking_scratch' and parsed.host in ('127.0.0.1','localhost')
e=create_engine(url)
with e.begin() as c:
 assert c.execute(text('select current_database()')).scalar_one()=='bf4ps_ranking_scratch'
 assert c.execute(text('select version_num from alembic_version')).scalar_one()=='0013_indexed_equipment_rankings'
 for id,name in [(1,'alpha'),(2,'beta'),(3,'gamma')]:
  c.execute(text("INSERT INTO soldiers(soldier_id,persona_id,platform,current_name,first_seen_at,last_seen_at) OVERRIDING SYSTEM VALUE VALUES (:id,:id,'pc',:name,now(),now())"),{'id':id,'name':name})
  c.execute(text("INSERT INTO collection_state(soldier_id,weapons_state,vehicles_state) VALUES (:id,'success','success')"),{'id':id})
 for id in [5,6]:
  c.execute(text("INSERT INTO weapon_catalog(weapon_id,weapon_guid,name,first_seen_at,last_seen_at) OVERRIDING SYSTEM VALUE VALUES (:id,:guid,:guid,now(),now())"),{'id':id,'guid':f'w{id}'})
 for id in [1,2,30,73]:
  c.execute(text("INSERT INTO vehicle_catalog(vehicle_id,vehicle_guid,name,first_seen_at,last_seen_at) OVERRIDING SYSTEM VALUE VALUES (:id,:guid,:guid,now(),now())"),{'id':id,'guid':f'v{id}'})
 for soldier,weapon,kills,secs,fired,hit in [(1,5,10,120,200,100),(2,5,10,60,100,50),(3,5,5,30,90,50),(1,6,3,60,100,101)]:
  c.execute(text("INSERT INTO soldier_weapon_stats(soldier_id,weapon_id,kills,headshots,shots_fired,shots_hit,time_equipped_seconds,source_fetched_at) VALUES (:s,:w,:k,0,:f,:h,:t,now())"),{'s':soldier,'w':weapon,'k':kills,'f':fired,'h':hit,'t':secs})
 for soldier,vehicle,kills,secs in [(1,1,10,100),(1,73,20,200),(1,2,5,60),(1,30,7,120),(2,1,15,60),(2,2,6,60),(2,30,6,60),(3,1,1,20)]:
  c.execute(text("INSERT INTO soldier_vehicle_stats(soldier_id,vehicle_id,kills,time_in_seconds,source_fetched_at) VALUES (:s,:v,:k,:t,now())"),{'s':soldier,'v':vehicle,'k':kills,'t':secs})
 process_window(c,0,2)
 process_window(c,2,4)
 def snapshot():
  return ([tuple(r) for r in c.execute(text('SELECT soldier_id,weapon_id,kills,kpm,accuracy FROM weapon_leaderboard_metrics ORDER BY soldier_id,weapon_id'))],
          [tuple(r) for r in c.execute(text('SELECT soldier_id,vehicle_id,kills,kpm FROM vehicle_leaderboard_metrics ORDER BY soldier_id,vehicle_id'))])
 first=snapshot()
 assert first[0]==[(1,5,10,Decimal('5'),Decimal('50')),(1,6,3,Decimal('3'),None),(2,5,10,Decimal('10'),Decimal('50')),(3,5,5,None,None)],first[0]
 assert first[1]==[(1,1,20,Decimal('6')),(1,2,12,Decimal('4')),(2,1,15,Decimal('15')),(2,2,12,Decimal('6')),(3,1,1,None)],first[1]
 # A weapon collection must not disturb vehicle metrics, and vice versa.
 from bf4ps.ranking_backfill import refresh_soldier_metrics
 c.execute(text('DELETE FROM vehicle_leaderboard_metrics WHERE soldier_id=1'))
 refresh_soldier_metrics(c,1,'weapons')
 assert c.execute(text('SELECT count(*) FROM vehicle_leaderboard_metrics WHERE soldier_id=1')).scalar_one()==0
 refresh_soldier_metrics(c,1,'vehicles')
 assert snapshot()==first
 # Simulate a failed collector transaction using a SAVEPOINT: no partial derived rows survive.
 nested=c.begin_nested()
 c.execute(text('UPDATE soldier_weapon_stats SET kills=999 WHERE soldier_id=1 AND weapon_id=5'))
 refresh_soldier_metrics(c,1,'weapons')
 assert c.execute(text('SELECT kills FROM weapon_leaderboard_metrics WHERE soldier_id=1 AND weapon_id=5')).scalar_one()==999
 nested.rollback()
 assert snapshot()==first,'rollback failed to restore derived state'
 process_window(c,0,2);process_window(c,2,4)
 assert snapshot()==first,'restart/idempotence mismatch'
 c.execute(text("UPDATE collection_state SET weapons_state='temporary_failure' WHERE soldier_id=2"))
 process_window(c,2,4)
 assert c.execute(text('SELECT count(*) FROM weapon_leaderboard_metrics WHERE soldier_id=2')).scalar_one()==0
 print('PASS: weapon KPM/accuracy gates, vehicle SUM/MAX families, null KPM, deterministic ties, window resume, idempotence and state exclusion',flush=True)
