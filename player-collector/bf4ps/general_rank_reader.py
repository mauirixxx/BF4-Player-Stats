"""Read published general rankings without recomputing population-wide windows.

Opt-in read model; not wired into the production website.
"""
from decimal import Decimal
from sqlalchemy import text
from .general_rank_publisher import METRICS, PLATFORMS


def query_page(conn, metric, platform, page=1, page_size=50, search='', division=0):
    if metric not in METRICS or platform not in PLATFORMS:
        raise ValueError('Invalid leaderboard metric/platform')
    if not 1 <= page <= 100000 or not 1 <= page_size <= 100 or not 0 <= division <= 10 or len(search)>100:
        raise ValueError('Invalid pagination/filter')
    params = dict(metric=metric, platform=platform, search=search,
                  pattern='%'+search.lower()+'%', division=division,
                  limit=page_size, offset=(page-1)*page_size)
    results = conn.execute(text('''
        WITH selected AS MATERIALIZED (
          SELECT g.generation_id,g.population
          FROM general_rank_published p
          JOIN general_rank_generations g ON g.generation_id=p.generation_id
          WHERE p.metric=:metric AND p.platform=:platform
            AND g.metric=p.metric AND g.platform=p.platform
            AND g.completed_at IS NOT NULL
        ), filtered AS MATERIALIZED (
          SELECT r.*,s.current_name,s.persona_id,s.platform,
                 selected.population,
                 r.rank*100.0/NULLIF(selected.population,0) AS top_pct
          FROM selected JOIN general_rank_rows r ON r.generation_id=selected.generation_id
          JOIN soldiers s ON s.soldier_id=r.soldier_id
          WHERE NOT EXISTS (SELECT 1 FROM player_exclusions pe
                            WHERE pe.platform=s.platform AND pe.persona_id=s.persona_id AND pe.active)
            AND (:division=0 OR r.division=:division)
            AND (:search='' OR lower(s.current_name) LIKE :pattern
                 OR s.persona_id::text LIKE :pattern
                 OR EXISTS (SELECT 1 FROM soldier_names n
                            WHERE n.soldier_id=s.soldier_id AND lower(n.name) LIKE :pattern))
        ), metadata AS (
          SELECT (SELECT population FROM selected) AS population,
                 count(*) AS filtered_count FROM filtered
        ), page_rows AS (
          SELECT * FROM filtered ORDER BY position LIMIT :limit OFFSET :offset
        )
        SELECT metadata.population AS cohort_population,metadata.filtered_count,
               p.soldier_id,p.current_name,p.persona_id,p.platform,p.value,
               p.hours_source_seconds,p.rank,p.position,p.population,p.top_pct,p.division,
               bp.country_code,bp.country_name,bp.battlelog_username,
               active_platoon.official_tag AS platoon_tag,
               active_platoon.linked_platoon_id::text AS platoon_id
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
    '''), params).mappings().all()
    if not results or results[0]['cohort_population'] is None:
        return None  # No published generation: caller must explicitly use legacy reader.
    population = int(results[0]['cohort_population'])
    filtered = int(results[0]['filtered_count'])
    rows = [{k:(float(v) if isinstance(v,Decimal) else v) for k,v in r.items()
             if k not in ('filtered_count','cohort_population')}
            for r in results if r['soldier_id'] is not None]
    return dict(population=population, filtered_count=filtered, page=page,
                page_size=page_size,total_pages=(filtered+page_size-1)//page_size,
                metric=metric,rows=rows)
