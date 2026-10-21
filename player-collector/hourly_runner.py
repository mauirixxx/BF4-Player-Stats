"""Bounded, resumable catalog-wide ranking refresh; one publisher across fleet.

Run inside the existing collector container with /rank mounted read-only.
A missing/failed scope never interrupts serving: the website falls back.
"""
import os
import subprocess
import sys
import time
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

URL = os.environ["BF4PS_DATABASE_URL"]
if make_url(URL).database != "bf4_playerstats":
    raise RuntimeError("refusing unexpected database")
MAX_JOBS = max(1, min(200, int(os.environ.get("BF4PS_RANK_MAX_JOBS", "50"))))
MAX_SECONDS = max(60, min(1740, int(os.environ.get("BF4PS_RANK_MAX_SECONDS", "1740"))))
MAX_JOB_SECONDS = max(30, min(180, int(os.environ.get("BF4PS_RANK_JOB_SECONDS", "120"))))
MIN_POPULATION = max(1, int(os.environ.get("BF4PS_RANK_MIN_POPULATION", "1")))
METRICS = {"weapon": ("kills", "kpm", "accuracy"), "vehicle": ("kills", "kpm")}
PLATFORMS = ("pc", "ps4", "xboxone", "all")
engine = create_engine(URL, pool_pre_ping=True)
started = time.monotonic()

# Single advisory-lock session held throughout all child builds.
with engine.connect() as conn:
    if not conn.execute(text("SELECT pg_try_advisory_lock(640041,170017)")).scalar_one():
        print("another rank builder holds the lease; exiting", flush=True)
        sys.exit(0)
    try:
        revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        if revision != "0017_rank_immutable_scores":
            raise RuntimeError("unexpected schema revision: " + str(revision))
        # A version row is mandatory: the publisher refuses untracked scopes.
        # Restrict to actual catalog populations to avoid thousands of empty scopes.
        catalog = conn.execute(text("""
            SELECT v.kind,v.item_id,v.platform,coalesce(ep.population,0) AS population
            FROM equipment_rank_scope_versions v
            JOIN (
                SELECT kind,item_id,platform,sum(population) AS population
                FROM equipment_population
                GROUP BY kind,item_id,platform
                UNION ALL
                SELECT kind,item_id,'all' AS platform,sum(population) AS population
                FROM equipment_population
                GROUP BY kind,item_id
            ) ep ON ep.kind=v.kind AND ep.item_id=v.item_id AND ep.platform=v.platform
            WHERE v.kind IN ('weapon','vehicle')
              AND v.platform IN ('pc','ps4','xboxone','all')
              AND ep.population >= :min_population
        """), {"min_population": MIN_POPULATION}).mappings().all()
        pointers = conn.execute(text("""
            SELECT p.kind,p.item_id,p.platform,p.metric,g.completed_at,g.status
            FROM equipment_rank_published p
            LEFT JOIN equipment_rank_generations g ON g.generation_id=p.generation_id
        """)).all()
        published = {(k,i,p,m): (when,status) for k,i,p,m,when,status in pointers}
        now = conn.execute(text("SELECT now()")).scalar_one()
        # Pick the ten highest aggregate-kill items per category, not ten soldiers.
        # The initial single-node rollout builds ALL-platform ranks, vehicles first.
        top_items = {}
        for kind, table, item_column in (
            ('vehicle', 'vehicle_leaderboard_metrics', 'vehicle_id'),
            ('weapon', 'weapon_leaderboard_metrics', 'weapon_id'),
        ):
            rows = conn.execute(text(f'''SELECT {item_column},sum(coalesce(kills,0)) AS total_kills
                FROM {table} GROUP BY {item_column}
                ORDER BY total_kills DESC,{item_column} LIMIT 10''')).all()
            top_items[kind] = [item for item, _ in rows]
            print('TOP 10',kind,rows,flush=True)
        eligible = {(r['kind'],r['item_id']) for r in catalog if r['platform']=='all'}
        candidates = []
        for kind in ('vehicle','weapon'):
            for item in top_items[kind]:
                if (kind,item) not in eligible:
                    continue
                for metric in METRICS[kind]:
                    key = (kind,item,'all',metric)
                    previous = published.get(key)
                    age = (now - previous[0]).total_seconds() if previous and previous[0] else None
                    if age is not None and age < 3300 and previous[1] == 'published':
                        continue
                    candidates.append((len(candidates),key))
        print(dict(catalog_scopes=len(catalog),pending=len(candidates),
                   budget=MAX_JOBS,seconds_budget=MAX_SECONDS),flush=True)
        attempted=0
        failures=0
        for _,(kind,item,platform,metric) in candidates:
            remaining = MAX_SECONDS - (time.monotonic()-started)
            if attempted >= MAX_JOBS or remaining < MAX_JOB_SECONDS + 15:
                print('BUDGET EXHAUSTED: deferring next job safely', round(remaining,1), flush=True)
                break
            args=[sys.executable,"/rank/build_rank_hourly.py","--kind",kind,
                  "--item",str(item),"--platform",platform,"--metric",metric,
                  "--publish","--production-ack"]
            attempted+=1
            print("BUILD",attempted,kind,item,platform,metric,flush=True)
            try:
                subprocess.run(args,check=True,timeout=min(MAX_JOB_SECONDS,remaining-5))
            except (subprocess.CalledProcessError,subprocess.TimeoutExpired) as exc:
                failures+=1
                print("BUILD FAILED",kind,item,platform,metric,str(exc),flush=True)
        print(dict(attempted=attempted,failed=failures,
                   deferred=len(candidates)-attempted,
                   seconds=round(time.monotonic()-started,1)),flush=True)
        if failures:
            sys.exit(1)
    finally:
        conn.execute(text("SELECT pg_advisory_unlock(640041,170017)"))
