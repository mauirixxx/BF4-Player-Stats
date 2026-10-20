"""Population changes during an admin exclusion transition.

Must run in the same transaction as moderation, with per-soldier ranking
advisory locks held before snapshots. Activated only with the population flag.
"""
from sqlalchemy import text

def affected_soldiers(conn, platform, persona_id):
    return [r[0] for r in conn.execute(text("""
        SELECT soldier_id FROM soldiers
        WHERE platform=:platform AND persona_id=:persona_id
        ORDER BY soldier_id
    """), {"platform":platform, "persona_id":persona_id})]

def lock_soldiers(conn, ids):
    for sid in ids:
        conn.execute(text("""
            SELECT pg_advisory_xact_lock(
                hashtextextended('bf4ps:ranking:' || CAST(:sid AS text), 0))
        """), {"sid":sid})

def snapshot(conn, kind, ids):
    if kind not in ("weapon", "vehicle"):
        raise ValueError("invalid kind")
    if not ids:
        return {}
    table="weapon_leaderboard_metrics" if kind=="weapon" else "vehicle_leaderboard_metrics"
    key="weapon_id" if kind=="weapon" else "vehicle_id"
    rows=conn.execute(text(f"""
        SELECT m.{key},s.platform,count(*) FROM {table} m
        JOIN soldiers s ON s.soldier_id=m.soldier_id
        WHERE m.soldier_id=ANY(:ids)
        AND NOT EXISTS (
            SELECT 1 FROM player_exclusions pe
            WHERE pe.platform=s.platform AND pe.persona_id=s.persona_id AND pe.active)
        GROUP BY m.{key},s.platform
    """), {"ids":ids})
    return {(int(item),platform):int(count) for item,platform,count in rows}

def apply(conn, kind, before, after):
    for item,platform in sorted(before.keys() | after.keys()):
        delta=after.get((item,platform),0)-before.get((item,platform),0)
        if not delta:
            continue
        p={"kind":kind,"item":item,"platform":platform,"delta":delta}
        if delta<0:
            result=conn.execute(text("""
                UPDATE equipment_population SET population=population+:delta
                WHERE kind=:kind AND item_id=:item AND platform=:platform
                AND population >= -:delta
            """),p)
            if result.rowcount!=1:
                raise RuntimeError("population baseline missing or insufficient")
        else:
            conn.execute(text("""
                INSERT INTO equipment_population(kind,item_id,platform,population)
                VALUES (:kind,:item,:platform,:delta)
                ON CONFLICT (kind,item_id,platform)
                DO UPDATE SET population=equipment_population.population+EXCLUDED.population
            """),p)
