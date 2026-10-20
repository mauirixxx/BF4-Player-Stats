"""Read-only fail-closed published generation eligibility check.

The caller MUST perform the rank-row read in the same transaction/snapshot.
Until all derived-table writers are instrumented, this is scratch-only.
"""
from sqlalchemy import text

QUERY=text('''SELECT g.generation_id FROM equipment_rank_published p
  JOIN equipment_rank_generations g ON g.generation_id=p.generation_id
  JOIN equipment_rank_scope_versions v ON v.kind=p.kind AND v.item_id=p.item_id AND v.platform=p.platform
  WHERE p.kind=:kind AND p.item_id=:item AND p.platform=:platform AND p.metric=:metric
    AND g.status='published' AND g.input_scope_version IS NOT NULL
    AND g.input_scope_version=v.version
    AND g.completed_at>=now()-(:max_age_seconds * interval '1 second')''')


def eligible_generation(conn,kind,item,platform,metric,max_age_seconds=300):
    if kind not in ('weapon','vehicle') or platform not in ('pc','ps4','xboxone','all'):
        raise ValueError('invalid scope')
    if metric not in (('kills','kpm','accuracy') if kind=='weapon' else ('kills','kpm')):
        raise ValueError('invalid metric')
    if item<1 or max_age_seconds<1:
        raise ValueError('invalid bounds')
    return conn.execute(QUERY,{'kind':kind,'item':item,'platform':platform,
                               'metric':metric,'max_age_seconds':max_age_seconds}).scalar_one_or_none()
