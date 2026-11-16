"""Opt-in published general ranking reader. No production activation."""
from decimal import Decimal
from sqlalchemy import text
from general_leaderboard import METRICS
PLATFORMS = frozenset(('all','pc','ps4','xboxone'))

def query_page(conn, metric, platform, page=1, page_size=50, search='', division=0):
    if metric not in METRICS or platform not in PLATFORMS:
        raise ValueError('Invalid leaderboard metric/platform')
    if not 1 <= page <= 100000 or not 1 <= page_size <= 100 or not 0 <= division <= 10 or len(search)>100:
        raise ValueError('Invalid pagination/filter')
    params = dict(metric=metric, platform=platform, search=search, pattern='%'+search.lower()+'%',
                  division=division, limit=page_size, offset=(page-1)*page_size)
    published = conn.execute(text("""
        SELECT g.generation_id,g.population,p.published_at FROM general_rank_published p
        JOIN general_rank_generations g ON g.generation_id=p.generation_id
        WHERE p.metric=:metric AND p.platform=:platform AND g.metric=p.metric
          AND g.platform=p.platform AND g.completed_at IS NOT NULL
    """), params).mappings().one_or_none()
    if published is None:
        return None
    population = int(published['population'])
    params['generation_id'] = published['generation_id']
    params['population'] = population
    # Snapshot ranks, positions and population are as-of publication. Current
    # exclusions and missing identities are filtered without renumbering ranks.
    filters = ["r.generation_id=:generation_id",
               "NOT EXISTS (SELECT 1 FROM player_exclusions pe WHERE pe.platform=s.platform AND pe.persona_id=s.persona_id AND pe.active)"]
    if division:
        filters.append("r.division=:division")
    if search:
        # Resolve matching identities first, allowing the existing trigram
        # indexes to drive name searches before intersecting snapshot rows.
        filters.append("""r.soldier_id IN (
            SELECT soldier_id FROM soldiers WHERE lower(current_name) LIKE :pattern
            UNION
            SELECT soldier_id FROM soldier_names WHERE lower(name) LIKE :pattern
            UNION
            SELECT soldier_id FROM soldiers WHERE persona_id::text LIKE :pattern
        )""")
    where = ' AND '.join(filters)
    filtered = int(conn.execute(text(f"""
        SELECT count(*) FROM general_rank_rows r JOIN soldiers s ON s.soldier_id=r.soldier_id
        WHERE {where}
    """), params).scalar_one())
    results = conn.execute(text(f"""
        WITH page_rows AS MATERIALIZED (
          SELECT r.*,s.current_name,s.persona_id,s.platform,
                 r.rank*100.0/NULLIF(:population,0) AS top_pct
          FROM general_rank_rows r JOIN soldiers s ON s.soldier_id=r.soldier_id
          WHERE {where} ORDER BY r.position LIMIT :limit OFFSET :offset
        )
        SELECT p.soldier_id,p.current_name,p.persona_id,p.platform,p.value,
               p.hours_source_seconds,p.rank,p.position,:population AS population,
               p.top_pct,p.division,bp.country_code,bp.country_name,bp.battlelog_username,
               active_platoon.official_tag AS platoon_tag,
               active_platoon.linked_platoon_id::text AS platoon_id
        FROM page_rows p
        LEFT JOIN LATERAL (
          SELECT b.country_code,b.country_name,b.battlelog_username
          FROM profile_soldiers ps JOIN battlelog_profiles b ON b.profile_id=ps.profile_id
          WHERE ps.soldier_id=p.soldier_id ORDER BY ps.last_seen_at DESC LIMIT 1
        ) bp ON true
        LEFT JOIN LATERAL (
          SELECT pl.tag AS official_tag,d.linked_platoon_id
          FROM platoon_soldier_discovery d JOIN platoons pl ON pl.platoon_id=d.linked_platoon_id
          WHERE d.soldier_id=p.soldier_id AND d.status='complete' AND pl.tag<>'' LIMIT 1
        ) active_platoon ON true ORDER BY p.position
    """), params).mappings().all()
    rows = [{k:(float(v) if isinstance(v,Decimal) else v) for k,v in r.items()} for r in results]
    return dict(population=population,filtered_count=filtered,page=page,page_size=page_size,
                total_pages=(filtered+page_size-1)//page_size,metric=metric,rows=rows,
                published_at=published['published_at'].isoformat(),generation_id=published['generation_id'])
