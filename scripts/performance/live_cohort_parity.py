"""Read-only live cohort comparison: raw stats vs proposed derived formulas."""
import os
from sqlalchemy import create_engine,text
from bf4ps.ranking_backfill import vehicle_family_sql,vehicle_mode_sql
engine=create_engine(os.environ['BF4PS_DATABASE_URL'])
with engine.connect() as c:
 c.execute(text('SET TRANSACTION READ ONLY'))
 c.execute(text("SET LOCAL statement_timeout='30000ms'"))
 assert c.execute(text('SELECT current_database()')).scalar_one()=='bf4_playerstats'
 print('source revision',c.execute(text('SELECT version_num FROM alembic_version')).scalar_one(),flush=True)
 for kind,item in [('weapon',5),('vehicle',1),('vehicle',2),('vehicle',41)]:
  for platform in ['all','pc']:
   filt='' if platform=='all' else 'AND s.platform=:platform'
   eligibility=f"JOIN soldiers s ON s.soldier_id=t.soldier_id JOIN collection_state cs ON cs.soldier_id=s.soldier_id WHERE cs.{kind}s_state='success' AND NOT EXISTS(SELECT 1 FROM player_exclusions pe WHERE pe.platform=s.platform AND pe.persona_id=s.persona_id AND pe.active) {filt}"
   if kind=='weapon':
    raw=f"SELECT t.soldier_id,MAX(t.kills) kills,MAX(t.time_equipped_seconds) seconds,CASE WHEN MAX(t.shots_fired)>=100 AND MAX(t.shots_hit)<=MAX(t.shots_fired) THEN MAX(t.shots_hit)::numeric*100/MAX(t.shots_fired) END accuracy FROM soldier_weapon_stats t {eligibility} AND t.weapon_id=:item GROUP BY t.soldier_id"
    derived=raw
   else:
    family=vehicle_family_sql().replace('v.vehicle_id','t.vehicle_id')
    mode=vehicle_mode_sql().replace('v.vehicle_id','t.vehicle_id')
    raw=f"WITH variants AS (SELECT t.soldier_id,t.vehicle_id,{family} family,{mode} mode,MAX(t.kills) kills,MAX(t.time_in_seconds) seconds FROM soldier_vehicle_stats t {eligibility} GROUP BY t.soldier_id,t.vehicle_id) SELECT soldier_id,CASE WHEN MAX(mode)='sum' THEN SUM(kills) ELSE MAX(kills) END kills,CASE WHEN MAX(mode)='sum' THEN SUM(seconds) ELSE MAX(seconds) END seconds,NULL::numeric accuracy FROM variants WHERE family=:item GROUP BY soldier_id"
    derived=raw
   params={'item':item,'platform':platform}
   for metric in (['kills','kpm','accuracy'] if kind=='weapon' else ['kills','kpm']):
    score=metric if metric!='kpm' else 'CASE WHEN seconds>=60 THEN kills::numeric*60/seconds END'
    q=f'WITH cohort AS ({raw}), ranked AS (SELECT soldier_id,{score} score,RANK() OVER(ORDER BY {score} DESC NULLS LAST) rank,ROW_NUMBER() OVER(ORDER BY {score} DESC NULLS LAST,soldier_id) position,COUNT(*) OVER() population FROM cohort) SELECT * FROM ranked ORDER BY score DESC NULLS LAST,soldier_id LIMIT 10'
    rows=c.execute(text(q),params).all()
    print(kind,item,platform,metric,'population',rows[0].population if rows else 0,'top10',len(rows),'first',rows[0].soldier_id if rows else None,flush=True)
