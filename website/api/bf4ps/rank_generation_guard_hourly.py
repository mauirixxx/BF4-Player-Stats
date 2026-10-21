"""Read-only fail-closed published generation eligibility check.

The caller MUST perform the rank-row read in the same transaction/snapshot.
Until all derived-table writers are instrumented, this is scratch-only.
"""
from sqlalchemy import text

QUERY=text('''SELECT g.generation_id FROM equipment_rank_published p
  JOIN equipment_rank_generations g ON g.generation_id=p.generation_id
  
  WHERE p.kind=:kind AND p.item_id=:item AND p.platform=:platform AND p.metric=:metric
    AND g.status='published' AND g.input_scope_version IS NOT NULL
    AND g.snapshot_format=1
    AND g.completed_at>=now()-(:max_age_seconds * interval '1 second')
    AND NOT EXISTS (SELECT 1 FROM equipment_rank_rows r JOIN soldiers s ON s.soldier_id=r.soldier_id JOIN player_exclusions x ON x.platform=s.platform AND x.persona_id=s.persona_id AND x.active WHERE r.generation_id=g.generation_id)''')


def eligible_generation(conn,kind,item,platform,metric,max_age_seconds=300):
    if kind not in ('weapon','vehicle') or platform not in ('pc','ps4','xboxone','all'):
        raise ValueError('invalid scope')
    if metric not in (('kills','kpm','accuracy') if kind=='weapon' else ('kills','kpm')):
        raise ValueError('invalid metric')
    if item<1 or max_age_seconds<1:
        raise ValueError('invalid bounds')
    return conn.execute(QUERY,{'kind':kind,'item':item,'platform':platform,
                               'metric':metric,'max_age_seconds':max_age_seconds}).scalar_one_or_none()