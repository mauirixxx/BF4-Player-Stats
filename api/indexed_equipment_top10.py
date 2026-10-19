"""Optional 0013 indexed equipment first-page rankings; disabled by default.

No write queries. The legacy full-cohort path remains authoritative for
search, divisions, pagination and non-Top-10 requests.
"""
import os
from sqlalchemy import text

METRICS={'weapon':{'kills','kpm','accuracy'},'vehicle':{'kills','kpm'}}
TABLES={'weapon':('weapon_leaderboard_metrics','weapon_id'),
        'vehicle':('vehicle_leaderboard_metrics','vehicle_id')}


def enabled():
    return os.environ.get('BF4PS_INDEXED_EQUIPMENT_READS') == '1'


def query_top10(conn,kind,platform,item,metric):
    if kind not in METRICS or metric not in METRICS[kind]:
        raise ValueError('unsupported equipment metric')
    if platform not in ('all','pc','ps4','xboxone') or not isinstance(item,int) or item<1:
        raise ValueError('invalid leaderboard cohort')
    table,key=TABLES[kind]
    params={'item':item,'platform':platform}
    eligibility=f'''FROM {table} m JOIN soldiers s ON s.soldier_id=m.soldier_id
       WHERE m.{key}=:item AND (:platform='all' OR s.platform=:platform)
         AND NOT EXISTS (SELECT 1 FROM public.player_exclusions pe
           WHERE pe.platform=s.platform AND pe.persona_id=s.persona_id AND pe.active)'''
    population=int(conn.execute(text('SELECT count(*) '+eligibility),params).scalar_one())
    fields='m.kills,m.kpm,m.accuracy' if kind=='weapon' else 'm.kills,m.kpm,NULL::numeric AS accuracy'
    rows=[dict(r) for r in conn.execute(text(f'''SELECT s.soldier_id,s.current_name,s.persona_id,s.platform,
        {fields},m.source_fetched_at
        {eligibility} ORDER BY m.{metric} DESC NULLS LAST,m.soldier_id LIMIT 10'''),params).mappings()]
    previous=object();rank=0
    for position,row in enumerate(rows,1):
        score=row[metric]
        if score!=previous:rank=position
        previous=score
        row['rank']=rank;row['position']=position
        pct=rank*100.0/population if population else 0.0
        row['top_pct']=pct
        row['division']=next((i for i,cutoff in enumerate((3,8,15,25,35,50,65,80,90),1) if pct<=cutoff),10)
    return {'population':population,'filtered_count':population,'page':1,
            'page_size':10,'total_pages':(population+9)//10,'rows':rows}
