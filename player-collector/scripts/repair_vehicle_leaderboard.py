"""Repair one vehicle's derived leaderboard metrics and population atomically.

Usage: BF4PS_DATABASE_URL=... python scripts/repair_vehicle_leaderboard.py --vehicle-id 42 --apply
Without --apply: read-only audit. No Battlelog requests.
"""
import argparse
import os
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

p=argparse.ArgumentParser()
p.add_argument("--vehicle-id",type=int,required=True)
p.add_argument("--apply",action="store_true")
a=p.parse_args()
if a.vehicle_id<=0: p.error("vehicle-id must be positive")
url=os.environ["BF4PS_DATABASE_URL"]
if make_url(url).database!="bf4_playerstats": raise RuntimeError("unexpected database")
engine=create_engine(url,pool_pre_ping=True)
with engine.begin() as c:
    c.execute(text("SET LOCAL lock_timeout='5s'"))
    c.execute(text("SET LOCAL statement_timeout='120s'"))
    revision=c.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    if revision!="0018_distributed_rank_queue": raise RuntimeError(f"unexpected schema {revision}")
    # Serialize concurrent repairs of the same vehicle.
    c.execute(text("SELECT pg_advisory_xact_lock(640043,:item)"),{"item":a.vehicle_id})
    raw=c.execute(text("""SELECT count(*) FROM soldier_vehicle_stats w
        JOIN soldiers s USING(soldier_id)
        JOIN collection_state cs USING(soldier_id)
        WHERE w.vehicle_id=:item AND cs.vehicles_state='success'
        AND NOT EXISTS(SELECT 1 FROM player_exclusions e
        WHERE e.platform=s.platform AND e.persona_id=s.persona_id AND e.active)"""),{"item":a.vehicle_id}).scalar_one()
    indexed=c.execute(text("SELECT count(*) FROM vehicle_leaderboard_metrics WHERE vehicle_id=:item"),{"item":a.vehicle_id}).scalar_one()
    print(dict(vehicle=a.vehicle_id,eligible_raw=raw,indexed=indexed,apply=a.apply),flush=True)
    if not a.apply: pass
    else:
        # Upsert only new or changed source snapshots; avoid rewriting 100k rows every run.
        upsert=c.execute(text("""INSERT INTO vehicle_leaderboard_metrics
          (soldier_id,vehicle_id,kills,kpm,source_fetched_at)
          SELECT w.soldier_id,w.vehicle_id,w.kills,
             CASE WHEN w.time_in_seconds>=60 THEN w.kills::numeric*60/w.time_in_seconds END,
             w.source_fetched_at
          FROM soldier_vehicle_stats w JOIN soldiers s USING(soldier_id)
          JOIN collection_state cs USING(soldier_id)
          WHERE w.vehicle_id=:item AND cs.vehicles_state='success'
            AND NOT EXISTS(SELECT 1 FROM player_exclusions e
              WHERE e.platform=s.platform AND e.persona_id=s.persona_id AND e.active)
          ON CONFLICT (soldier_id,vehicle_id) DO UPDATE
          SET kills=EXCLUDED.kills,kpm=EXCLUDED.kpm,
              source_fetched_at=EXCLUDED.source_fetched_at
          WHERE vehicle_leaderboard_metrics.source_fetched_at < EXCLUDED.source_fetched_at
             OR vehicle_leaderboard_metrics.kills IS DISTINCT FROM EXCLUDED.kills
             OR vehicle_leaderboard_metrics.kpm IS DISTINCT FROM EXCLUDED.kpm
"""),{"item":a.vehicle_id}).rowcount
        # Recalculate population using exactly the eligible derived cohort.
        counts=c.execute(text("""SELECT s.platform,count(*) AS n FROM vehicle_leaderboard_metrics m
            JOIN soldiers s USING(soldier_id) WHERE m.vehicle_id=:item
            AND NOT EXISTS(SELECT 1 FROM player_exclusions e
                WHERE e.platform=s.platform AND e.persona_id=s.persona_id AND e.active)
            GROUP BY s.platform"""),{"item":a.vehicle_id}).all()
        for platform,n in counts:
            c.execute(text("""INSERT INTO equipment_population(kind,item_id,platform,population)
              VALUES('vehicle',:item,:platform,:n)
              ON CONFLICT(kind,item_id,platform) DO UPDATE SET population=EXCLUDED.population"""),
              {"item":a.vehicle_id,"platform":platform,"n":n})
        # Only invalidate ranking publishers when the read model actually changed.
        if upsert:
            c.execute(text("""UPDATE equipment_rank_scope_versions SET version=version+1
               WHERE kind='vehicle' AND item_id=:item"""),{"item":a.vehicle_id})
        print(dict(upserted=upsert,populations=dict(counts)),flush=True)
