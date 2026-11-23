"""Published general ranking read path. None means no published snapshot for scope."""
from decimal import Decimal
from sqlalchemy import text

def query_snapshot_page(conn, metric, platform, page=1, page_size=50, search='', division=0):
    # Only a complete, published generation can be served.
    pointer=conn.execute(text("""
        SELECT p.generation_id,g.population
        FROM general_rank_published p
        JOIN general_rank_generations g ON g.generation_id=p.generation_id
        WHERE p.metric=:metric AND p.platform=:platform
          AND g.metric=p.metric AND g.platform=p.platform
          AND g.completed_at IS NOT NULL
    """),{'metric':metric,'platform':platform}).mappings().first()
    if pointer is None:
        return None
    if not search and division==0:
        from general_rank_snapshot_fast import query_fast_page
        return query_fast_page(conn,int(pointer['generation_id']),int(pointer['population']),metric,page,page_size)
    params={'generation':int(pointer['generation_id']),'division':division,
            'search':search,'pattern':'%'+search.lower()+'%',
            'limit':page_size,'offset':(page-1)*page_size}
    # Snapshot positions/ranks are global. Filter only after the published ranking.
    result=conn.execute(text("""
        WITH filtered AS MATERIALIZED (
          SELECT r.position,r.soldier_id,r.value,r.rank,r.division,
                 r.hours_source_seconds,s.current_name,s.persona_id,s.platform
          FROM general_rank_rows r
          JOIN soldiers s ON s.soldier_id=r.soldier_id
          WHERE r.generation_id=:generation
            AND (:division=0 OR r.division=:division)
            AND (:search='' OR lower(s.current_name) LIKE :pattern
              OR s.persona_id::text LIKE :pattern
              OR EXISTS (SELECT 1 FROM soldier_names n
                         WHERE n.soldier_id=s.soldier_id AND lower(n.name) LIKE :pattern))
        ), metadata AS (
          SELECT count(*) AS filtered_count FROM filtered
        ), page_rows AS (
          SELECT * FROM filtered ORDER BY position LIMIT :limit OFFSET :offset
        )
        SELECT metadata.filtered_count,
               p.soldier_id,p.current_name,p.persona_id,p.platform,p.value,
               p.hours_source_seconds,
               bp.country_code,bp.country_name,bp.battlelog_username,
               active_platoon.official_tag AS platoon_tag,
               active_platoon.linked_platoon_id::text AS platoon_id,
               p.rank,p.position,p.division
        FROM metadata LEFT JOIN page_rows p ON true
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
    population=int(pointer['population'])
    filtered=int(result[0]['filtered_count'])
    rows=[]
    for item in result:
        if item['soldier_id'] is None:
            continue
        row={k:v for k,v in item.items() if k!='filtered_count'}
        row['population']=population
        row['top_pct']=float(Decimal(row['rank'])*100/Decimal(population)) if population else None
        rows.append(row)
    return {'population':population,'filtered_count':filtered,'page':page,
            'page_size':page_size,'total_pages':(filtered+page_size-1)//page_size,
            'metric':metric,'rows':rows}
