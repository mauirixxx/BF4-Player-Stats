from sqlalchemy import text

def query_fast_page(conn, generation, population, metric, page, page_size):
    params={'generation':generation,'limit':page_size,'offset':(page-1)*page_size}
    result=conn.execute(text("""
        WITH page_rows AS MATERIALIZED (
          SELECT r.soldier_id,r.value,r.rank,r.position,r.division,
                 r.hours_source_seconds
          FROM general_rank_rows r
          WHERE r.generation_id=:generation
          ORDER BY r.position LIMIT :limit OFFSET :offset
        )
        SELECT p.soldier_id,s.current_name,s.persona_id,s.platform,p.value,
               p.hours_source_seconds,
               bp.country_code,bp.country_name,bp.battlelog_username,
               active_platoon.official_tag AS platoon_tag,
               active_platoon.linked_platoon_id::text AS platoon_id,
               p.rank,p.position,p.division
        FROM page_rows p
        JOIN soldiers s ON s.soldier_id=p.soldier_id
        LEFT JOIN LATERAL (
          SELECT b.country_code,b.country_name,b.battlelog_username
          FROM profile_soldiers ps JOIN battlelog_profiles b ON b.profile_id=ps.profile_id
          WHERE ps.soldier_id=p.soldier_id ORDER BY ps.last_seen_at DESC LIMIT 1
        ) bp ON true
        LEFT JOIN LATERAL (
          SELECT pl.tag AS official_tag,d.linked_platoon_id
          FROM platoon_soldier_discovery d JOIN platoons pl ON pl.platoon_id=d.linked_platoon_id
          WHERE d.soldier_id=p.soldier_id AND d.status='complete' AND pl.tag<>'' LIMIT 1
        ) active_platoon ON true
        ORDER BY p.position
    """),params).mappings().all()
    rows=[]
    for item in result:
        row=dict(item)
        row['population']=population
        row['top_pct']=float(row['rank'])*100.0/population if population else None
        rows.append(row)
    return {'population':population,'filtered_count':population,'page':page,
            'page_size':page_size,'total_pages':(population+page_size-1)//page_size,
            'metric':metric,'rows':rows}