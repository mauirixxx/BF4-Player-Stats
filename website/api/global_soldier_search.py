"""Bounded global soldier search, including identities without detailed stats."""
from sqlalchemy import text

SEARCH_SQL = text('''
SELECT s.soldier_id,s.current_name,s.persona_id,s.platform,
       d.rank,d.kills,cs.detailed_state,bp.battlelog_username,
       bp.country_code,bp.country_name
FROM soldiers s
LEFT JOIN collection_state cs ON cs.soldier_id=s.soldier_id
LEFT JOIN detailed_stats_current d ON d.soldier_id=s.soldier_id
LEFT JOIN LATERAL (
 SELECT b.battlelog_username,b.country_code,b.country_name
 FROM profile_soldiers ps JOIN battlelog_profiles b ON b.profile_id=ps.profile_id
 WHERE ps.soldier_id=s.soldier_id ORDER BY ps.last_seen_at DESC LIMIT 1
) bp ON true
WHERE NOT EXISTS (SELECT 1 FROM public.player_exclusions pe WHERE pe.platform=s.platform AND pe.persona_id=s.persona_id AND pe.active) AND (lower(s.current_name) LIKE :pattern ESCAPE '\\'
   OR s.persona_id::text LIKE :pattern ESCAPE '\\'
   OR EXISTS (SELECT 1 FROM soldier_names n WHERE n.soldier_id=s.soldier_id
              AND lower(n.name) LIKE :pattern ESCAPE '\\'))
ORDER BY (lower(s.current_name)=:exact) DESC,
         (s.persona_id::text=:exact) DESC,
         s.soldier_id
LIMIT 100
''')

def search_soldiers(conn, term):
    term=term.strip()
    if not 2<=len(term)<=80:
        raise ValueError('Search must be 2-80 characters')
    escaped=term.lower().replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
    rows=conn.execute(SEARCH_SQL,{'pattern':'%'+escaped+'%','exact':term.lower()}).mappings()
    return {'rows':[dict(r) for r in rows]}
