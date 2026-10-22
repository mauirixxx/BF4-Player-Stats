"""Repair one weapon's derived leaderboard metrics and population atomically.

Usage: BF4PS_DATABASE_URL=... python scripts/repair_weapon_leaderboard.py --weapon-id 42 --apply
Without --apply: read-only audit. No Battlelog requests.
"""
import argparse
import os
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

p=argparse.ArgumentParser()
p.add_argument("--weapon-id",type=int,required=True)
p.add_argument("--apply",action="store_true")
a=p.parse_args()
if a.weapon_id<=0: p.error("weapon-id must be positive")
url=os.environ["BF4PS_DATABASE_URL"]
if make_url(url).database!="bf4_playerstats": raise RuntimeError("unexpected database")
engine=create_engine(url,pool_pre_ping=True)
with engine.begin() as c:
    c.execute(text("SET LOCAL lock_timeout='5s'"))
    c.execute(text("SET LOCAL statement_timeout='120s'"))
    revision=c.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    if revision!="0018_distributed_rank_queue": raise RuntimeError(f"unexpected schema {revision}")
    # Serialize concurrent repairs of the same weapon.
    c.execute(text("SELECT pg_advisory_xact_lock(640042,:item)"),{"item":a.weapon_id})
    raw=c.execute(text("""SELECT count(*) FROM soldier_weapon_stats w
        JOIN soldiers s USING(soldier_id)
        JOIN collection_state cs USING(soldier_id)
        WHERE w.weapon_id=:item AND cs.weapons_state='success'
        AND NOT EXISTS(SELECT 1 FROM player_exclusions e
        WHERE e.platform=s.platform AND e.persona_id=s.persona_id AND e.active)"""),{"item":a.weapon_id}).scalar_one()
    indexed=c.execute(text("SELECT count(*) FROM weapon_leaderboard_metrics WHERE weapon_id=:item"),{"item":a.weapon_id}).scalar_one()
    print(dict(weapon=a.weapon_id,eligible_raw=raw,indexed=indexed,apply=a.apply),flush=True)
    if not a.apply: pass
    else:
        # Upsert only new or changed source snapshots; avoid rewriting 100k rows every run.
        upsert=c.execute(text("""INSERT INTO weapon_leaderboard_metrics
          (soldier_id,weapon_id,kills,kpm,accuracy,source_fetched_at)
          SELECT w.soldier_id,w.weapon_id,w.kills,
             CASE WHEN w.time_equipped_seconds>=60 THEN w.kills::numeric*60/w.time_equipped_seconds END,
             CASE WHEN w.shots_fired>=100 AND w.shots_hit<=w.shots_fired
                  THEN w.shots_hit::numeric*100/w.shots_fired END,
             w.source_fetched_at
          FROM soldier_weapon_stats w JOIN soldiers s USING(soldier_id)
          JOIN collection_state cs USING(soldier_id)
          WHERE w.weapon_id=:item AND cs.weapons_state='success'
            AND NOT EXISTS(SELECT 1 FROM player_exclusions e
              WHERE e.platform=s.platform AND e.persona_id=s.persona_id AND e.active)
          ON CONFLICT (soldier_id,weapon_id) DO UPDATE
          SET kills=EXCLUDED.kills,kpm=EXCLUDED.kpm,accuracy=EXCLUDED.accuracy,
              source_fetched_at=EXCLUDED.source_fetched_at
          WHERE weapon_leaderboard_metrics.source_fetched_at < EXCLUDED.source_fetched_at
             OR weapon_leaderboard_metrics.kills IS DISTINCT FROM EXCLUDED.kills
             OR weapon_leaderboard_metrics.kpm IS DISTINCT FROM EXCLUDED.kpm
             OR weapon_leaderboard_metrics.accuracy IS DISTINCT FROM EXCLUDED.accuracy"""),{"item":a.weapon_id}).rowcount
        # Recalculate population using exactly the eligible derived cohort.
        counts=c.execute(text("""SELECT s.platform,count(*) AS n FROM weapon_leaderboard_metrics m
            JOIN soldiers s USING(soldier_id) WHERE m.weapon_id=:item
            AND NOT EXISTS(SELECT 1 FROM player_exclusions e
                WHERE e.platform=s.platform AND e.persona_id=s.persona_id AND e.active)
            GROUP BY s.platform"""),{"item":a.weapon_id}).all()
        for platform,n in counts:
            c.execute(text("""INSERT INTO equipment_population(kind,item_id,platform,population)
              VALUES('weapon',:item,:platform,:n)
              ON CONFLICT(kind,item_id,platform) DO UPDATE SET population=EXCLUDED.population"""),
              {"item":a.weapon_id,"platform":platform,"n":n})
        # Only invalidate ranking publishers when the read model actually changed.
        if upsert:
            c.execute(text("""UPDATE equipment_rank_scope_versions SET version=version+1
               WHERE kind='weapon' AND item_id=:item"""),{"item":a.weapon_id})
        print(dict(upserted=upsert,populations=dict(counts)),flush=True)
