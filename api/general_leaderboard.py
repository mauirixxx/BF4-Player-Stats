"""Read-only paginated general rankings. Never rank only the visible page."""
from decimal import Decimal
from sqlalchemy import text

METRICS = frozenset(('kills','total_score','wins','time_played_seconds',
    'conquest_score','rush_score','team_deathmatch_score','domination_score',
    'obliteration_score','defuse_score','capture_the_flag_score',
    'air_superiority_score','carrier_assault_score','chain_link_score'))
CUTS = (3,8,15,25,35,50,65,80,90)

def query_page(conn, metric, platform, page=1, page_size=50, search='', division=0):
    if metric not in METRICS or platform not in ('all','pc','ps4','xboxone'):
        raise ValueError('Invalid leaderboard metric/platform')
    if not 1 <= page <= 100000 or not 1 <= page_size <= 100 or not 0 <= division <= 10 or len(search)>100:
        raise ValueError('Invalid pagination/filter')
    # The metric identifier is interpolated only after strict allowlisting.
    # Rank before search/division/page so ties and divisions stay global.
    sql = f'''
      WITH cohort AS (
        SELECT s.soldier_id,s.current_name,s.persona_id,s.platform,
               d.{metric} AS value
        FROM soldiers s
        JOIN collection_state cs ON cs.soldier_id=s.soldier_id
        JOIN detailed_stats_current d ON d.soldier_id=s.soldier_id
        WHERE cs.detailed_state='success' AND d.{metric} IS NOT NULL AND NOT EXISTS (SELECT 1 FROM public.player_exclusions pe WHERE pe.platform=s.platform AND pe.persona_id=s.persona_id AND pe.active)
          AND (:platform='all' OR s.platform=:platform)
      ), ranked AS (
        SELECT *,rank() OVER (ORDER BY value DESC) AS rank,
               row_number() OVER (ORDER BY value DESC,soldier_id) AS position,
               count(*) OVER () AS population FROM cohort
      ), decorated AS (
        SELECT *,rank*100.0/nullif(population,0) AS top_pct,
          CASE {' '.join(f'WHEN rank*100.0/nullif(population,0)<={cut} THEN {i}' for i,cut in enumerate(CUTS,1))}
               ELSE 10 END AS division
        FROM ranked
      ), filtered AS (
        SELECT * FROM decorated r
        WHERE (:search='' OR lower(r.current_name) LIKE :pattern
          OR r.persona_id::text LIKE :pattern
          OR EXISTS (SELECT 1 FROM soldier_names n WHERE n.soldier_id=r.soldier_id AND lower(n.name) LIKE :pattern))
          AND (:division=0 OR r.division=:division)
      )
    '''
    params={'platform':platform,'search':search,'pattern':'%'+search.lower()+'%',
            'division':division,'limit':page_size,'offset':(page-1)*page_size}
    meta=conn.execute(text(sql+'SELECT count(*) AS filtered_count,coalesce(max(population),0) AS population FROM filtered'),params).mappings().one()
    population=int(meta['population'])
    if not population:
        population=int(conn.execute(text(sql+'SELECT count(*) FROM cohort'),params).scalar_one())
    rows=[dict(r) for r in conn.execute(text(sql+'''
       SELECT p.soldier_id,p.current_name,p.persona_id,p.platform,p.value,
              bp.country_code,bp.country_name,bp.battlelog_username,active_platoon.displayed_tag AS platoon_tag,
              p.rank,p.position,p.population,p.top_pct,p.division
       FROM (SELECT * FROM filtered ORDER BY value DESC,soldier_id LIMIT :limit OFFSET :offset) p
       LEFT JOIN LATERAL (
         SELECT b.country_code,b.country_name,b.battlelog_username
         FROM profile_soldiers ps JOIN battlelog_profiles b ON b.profile_id=ps.profile_id
         WHERE ps.soldier_id=p.soldier_id ORDER BY ps.last_seen_at DESC LIMIT 1
       ) bp ON true
       LEFT JOIN LATERAL (
         SELECT d.displayed_tag
         FROM platoon_soldier_discovery d
         WHERE d.soldier_id=p.soldier_id AND d.linked_platoon_id IS NOT NULL
           AND d.displayed_tag IS NOT NULL AND d.displayed_tag<>''
         LIMIT 1
       ) active_platoon ON true
       ORDER BY p.value DESC,p.soldier_id
    '''),params).mappings()]
    for row in rows:
        for key,value in row.items():
            if isinstance(value,Decimal):
                row[key]=float(value)
    filtered=int(meta['filtered_count'])
    return {'population':population,'filtered_count':filtered,'page':page,
            'page_size':page_size,'total_pages':(filtered+page_size-1)//page_size,
            'metric':metric,'rows':rows}
