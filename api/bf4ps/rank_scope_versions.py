"""Transaction-local invalidation of ranking scopes; caller owns commit."""
from sqlalchemy import text


def invalidate(conn, scopes):
    """Bump each platform scope and its all-platform counterpart once."""
    keys=set()
    for kind,item,platform in scopes:
        if kind not in ('weapon','vehicle') or platform not in ('pc','ps4','xboxone') or int(item)<1:
            raise ValueError('invalid ranking scope')
        keys.add((kind,int(item),platform))
        keys.add((kind,int(item),'all'))
    for kind,item,platform in sorted(keys):
        conn.execute(text('''INSERT INTO equipment_rank_scope_versions(kind,item_id,platform,version)
            VALUES (:kind,:item,:platform,1)
            ON CONFLICT(kind,item_id,platform) DO UPDATE SET
              version=equipment_rank_scope_versions.version+1,changed_at=now()'''),
            {'kind':kind,'item':item,'platform':platform})
    return len(keys)


def snapshot_scopes(conn, kind, start, stop):
    """Read all scopes for a soldier window, including zero-score members."""
    if kind not in ('weapon','vehicle'):
        raise ValueError('invalid kind')
    table='weapon_leaderboard_metrics' if kind=='weapon' else 'vehicle_leaderboard_metrics'
    item='weapon_id' if kind=='weapon' else 'vehicle_id'
    return {(kind,int(i),p) for i,p in conn.execute(text(f'''
        SELECT DISTINCT m.{item},s.platform FROM {table} m
        JOIN soldiers s ON s.soldier_id=m.soldier_id
        WHERE m.soldier_id>=:start AND m.soldier_id<:stop'''),{'start':start,'stop':stop})}


def invalidate_soldier(conn, soldier_id, old_platform=None):
    """Invalidate all indexed equipment for a soldier after moderation/platform change.

    Invoke in the SAME transaction as the change; old_platform is required
    when a soldier's platform has changed.
    """
    soldier=conn.execute(text('SELECT platform FROM soldiers WHERE soldier_id=:sid'),
                         {'sid':soldier_id}).scalar_one()
    platforms={soldier}
    if old_platform is not None:
        if old_platform not in ('pc','ps4','xboxone'):
            raise ValueError('invalid old platform')
        platforms.add(old_platform)
    scopes=set()
    for kind in ('weapon','vehicle'):
        current=snapshot_scopes(conn,kind,soldier_id,soldier_id+1)
        for _,item,_ in current:
            scopes.update((kind,item,p) for p in platforms)
    return invalidate(conn,scopes)
