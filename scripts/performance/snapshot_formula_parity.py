"""Read-only, repeatable-read comparison of legacy vehicle family and derived aggregation."""
import os
from sqlalchemy import create_engine,text
from bf4ps.ranking_backfill import vehicle_family_sql,vehicle_mode_sql
engine=create_engine(os.environ['BF4PS_DATABASE_URL'])
with engine.connect() as c:
 c.execute(text('BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
 c.execute(text("SET LOCAL statement_timeout='120000ms'"))
 assert c.execute(text('SELECT current_database()')).scalar_one()=='bf4_playerstats'
 snapshot=c.execute(text('SELECT txid_current_snapshot()::text')).scalar_one()
 print('consistent snapshot',snapshot,flush=True)
 for item in (1,2,41,4,62):
  for platform in ('all','pc'):
   filt='' if platform=='all' else 'AND s.platform=:platform'
   base=f"FROM soldier_vehicle_stats t JOIN soldiers s ON s.soldier_id=t.soldier_id JOIN collection_state cs ON cs.soldier_id=t.soldier_id WHERE cs.vehicles_state='success' AND NOT EXISTS(SELECT 1 FROM player_exclusions pe WHERE pe.platform=s.platform AND pe.persona_id=s.persona_id AND pe.active) {filt}"
   fam=vehicle_family_sql().replace('v.vehicle_id','t.vehicle_id')
   mode=vehicle_mode_sql().replace('v.vehicle_id','t.vehicle_id')
   ids=[raw for raw,(canonical,_) in __import__('bf4ps.ranking_backfill',fromlist=['FAMILIES']).FAMILIES.items() if canonical==item]+[item]
   old=f"WITH raw AS (SELECT t.soldier_id,t.vehicle_id,MAX(t.kills) kills,MAX(t.time_in_seconds) seconds {base} AND t.vehicle_id=ANY(:ids) GROUP BY t.soldier_id,t.vehicle_id), variants AS (SELECT soldier_id,{fam.replace('t.vehicle_id','vehicle_id')} family,{mode.replace('t.vehicle_id','vehicle_id')} mode,kills,seconds FROM raw), grouped AS (SELECT soldier_id,CASE WHEN MAX(mode)='sum' THEN SUM(kills) ELSE MAX(kills) END kills,CASE WHEN MAX(mode)='sum' THEN SUM(seconds) ELSE MAX(seconds) END seconds FROM variants WHERE family=:item GROUP BY soldier_id) SELECT soldier_id,kills,CASE WHEN seconds>=60 THEN kills::numeric*60/seconds END kpm FROM grouped"
   new=f"WITH raw AS (SELECT t.soldier_id,{fam} family,{mode} mode,MAX(t.kills) kills,MAX(t.time_in_seconds) seconds {base} GROUP BY t.soldier_id,t.vehicle_id), grouped AS (SELECT soldier_id,CASE WHEN MAX(mode)='sum' THEN SUM(kills) ELSE MAX(kills) END kills,CASE WHEN MAX(mode)='sum' THEN SUM(seconds) ELSE MAX(seconds) END seconds FROM raw WHERE family=:item GROUP BY soldier_id) SELECT soldier_id,kills,CASE WHEN seconds>=60 THEN kills::numeric*60/seconds END kpm FROM grouped"
   args={'item':item,'ids':ids,'platform':platform}
   for metric in ('kills','kpm'):
    query=f"WITH legacy AS ({old}), proposed AS ({new}) SELECT (SELECT COUNT(*) FROM legacy) old_count,(SELECT COUNT(*) FROM proposed) new_count,(SELECT COUNT(*) FROM ((SELECT * FROM legacy EXCEPT ALL SELECT * FROM proposed) UNION ALL (SELECT * FROM proposed EXCEPT ALL SELECT * FROM legacy)) mismatch) mismatches"
    result=c.execute(text(query),args).one()
    assert result.old_count==result.new_count and result.mismatches==0,(item,platform,metric,result)
    print('PASS vehicle',item,platform,metric,'population',result.old_count,flush=True)
 c.rollback()
