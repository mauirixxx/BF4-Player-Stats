"""Opt-in precomputed equipment ranking API; scratch validated, no live cutover.

Call in a REPEATABLE READ, READ ONLY transaction. Return None for fallback.
"""
from sqlalchemy import text
from bf4ps.rank_generation_guard_hourly import eligible_generation

DIVISION_CUTOFFS=(3,8,15,25,35,50,65,80,90)


def get_precomputed_page(conn,kind,platform,item,page,page_size,search,division,metric):
    if kind not in ('weapon','vehicle') or platform not in ('pc','ps4','xboxone','all'):
        return None
    if metric not in (('kills','kpm','accuracy') if kind=='weapon' else ('kills','kpm')):
        return None
    if page<1 or page_size<1 or page_size>100 or division not in range(11) or item<1:
        return None
    generation=eligible_generation(conn,kind,item,platform,metric,10800)
    if generation is None:return None
    p={'g':generation,'item':item,'search':'%'+search.lower()+'%',
       'division':division,'limit':page_size,'offset':(page-1)*page_size}
    # Rank is competition rank, position is deterministic stable order.
    source=f'''FROM equipment_rank_rows r
      JOIN soldiers s ON s.soldier_id=r.soldier_id
      JOIN equipment_rank_generations g ON g.generation_id=r.generation_id
      WHERE r.generation_id=:g'''
    accuracy_expr = "r.snapshot_accuracy AS accuracy"
    filtered=f'''SELECT r.soldier_id,s.current_name,s.persona_id,s.platform,
      r.snapshot_kills AS kills,r.snapshot_kpm AS kpm,{accuracy_expr},r.snapshot_source_fetched_at AS source_fetched_at,r.rank,r.position,
      r.rank*100.0/nullif(g.row_count,0) AS top_pct,
      CASE WHEN r.rank*100.0/nullif(g.row_count,0)<=3 THEN 1
           WHEN r.rank*100.0/nullif(g.row_count,0)<=8 THEN 2
           WHEN r.rank*100.0/nullif(g.row_count,0)<=15 THEN 3
           WHEN r.rank*100.0/nullif(g.row_count,0)<=25 THEN 4
           WHEN r.rank*100.0/nullif(g.row_count,0)<=35 THEN 5
           WHEN r.rank*100.0/nullif(g.row_count,0)<=50 THEN 6
           WHEN r.rank*100.0/nullif(g.row_count,0)<=65 THEN 7
           WHEN r.rank*100.0/nullif(g.row_count,0)<=80 THEN 8
           WHEN r.rank*100.0/nullif(g.row_count,0)<=90 THEN 9 ELSE 10 END AS division
      {source} AND (:search='%%' OR lower(s.current_name) LIKE :search OR s.persona_id::text LIKE :search)'''
    # Derive filtered count and page rows from the same snapshot.
    count=conn.execute(text('SELECT count(*) FROM ('+filtered+') f WHERE (:division=0 OR division=:division)'),p).scalar_one()
    rows=[dict(r) for r in conn.execute(text('SELECT * FROM ('+filtered+') f WHERE (:division=0 OR division=:division) ORDER BY position LIMIT :limit OFFSET :offset'),p).mappings()]
    population=conn.execute(text('SELECT row_count FROM equipment_rank_generations WHERE generation_id=:g'),p).scalar_one()
    return {'population':int(population),'filtered_count':int(count),'page':page,'page_size':page_size,
            'total_pages':(int(count)+page_size-1)//page_size,'rows':rows,'rank_updated_at':conn.execute(text('SELECT completed_at FROM equipment_rank_generations WHERE generation_id=:g'),p).scalar_one()}