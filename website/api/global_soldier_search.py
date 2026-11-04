"""Indexed, bounded global soldier search, including historical aliases.

Collect matching identity IDs first; only enrich the bounded candidate set.
"""
from sqlalchemy import text

SEARCH_SQL = text(r"""
WITH candidates AS MATERIALIZED (
    SELECT soldier_id FROM (
        SELECT soldier_id
        FROM soldiers
        WHERE lower(current_name) LIKE :pattern ESCAPE '\'
        ORDER BY (lower(current_name)=:exact) DESC, soldier_id
        LIMIT 100
    ) current_hits
    UNION
    SELECT soldier_id FROM (
        SELECT DISTINCT soldier_id
        FROM soldier_names
        WHERE lower(name) LIKE :pattern ESCAPE '\'
        LIMIT 100
    ) alias_hits
    UNION
    SELECT soldier_id FROM (
        SELECT soldier_id FROM soldiers
        WHERE persona_id=CAST(:persona_id AS bigint)
        LIMIT 100
    ) persona_hits
),
matches AS MATERIALIZED (
    SELECT s.soldier_id,s.current_name,s.persona_id,s.platform
    FROM candidates x JOIN soldiers s ON s.soldier_id=x.soldier_id
    WHERE NOT EXISTS (
      SELECT 1 FROM public.player_exclusions pe
      WHERE pe.platform=s.platform AND pe.persona_id=s.persona_id AND pe.active
    )
    ORDER BY (lower(s.current_name)=:exact) DESC,
             (s.persona_id::text=:exact) DESC,s.soldier_id
    LIMIT 100
)
SELECT s.soldier_id,s.current_name,s.persona_id,s.platform,
       d.rank,d.kills,cs.detailed_state,bp.battlelog_username,
       bp.country_code,bp.country_name
FROM matches s
LEFT JOIN collection_state cs ON cs.soldier_id=s.soldier_id
LEFT JOIN detailed_stats_current d ON d.soldier_id=s.soldier_id
LEFT JOIN LATERAL (
 SELECT b.battlelog_username,b.country_code,b.country_name
 FROM profile_soldiers ps JOIN battlelog_profiles b ON b.profile_id=ps.profile_id
 WHERE ps.soldier_id=s.soldier_id ORDER BY ps.last_seen_at DESC LIMIT 1
) bp ON true
ORDER BY (lower(s.current_name)=:exact) DESC,
         (s.persona_id::text=:exact) DESC,s.soldier_id
""")

def search_soldiers(conn, term):
    term=term.strip()
    if not 2<=len(term)<=80:
        raise ValueError('Search must be 2-80 characters')
    escaped=term.lower().replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
    persona_id=int(term) if term.isdecimal() and len(term)<=19 and int(term)<=9223372036854775807 else None
    rows=conn.execute(SEARCH_SQL,{'pattern':'%'+escaped+'%','exact':term.lower(),'persona_id':persona_id}).mappings()
    return {'rows':[dict(r) for r in rows]}
