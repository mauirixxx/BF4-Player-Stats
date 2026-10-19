"""Restartable bounded derived leaderboard backfill; explicit scratch/production opt-in.

Runs one transaction per soldier-ID window, recomputing rows from local PostgreSQL
only. Existing derived rows for each window are replaced atomically. Never calls
Battlelog. Run only after migration 0013 and collector synchronization are ready.
"""
from __future__ import annotations
import argparse
import os
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

# Canonical mapping mirrors audited public API; second member is SUM or MAX.
FAMILIES = {2:(2,'sum'),30:(2,'sum'),41:(41,'sum'),63:(41,'sum'),47:(47,'max'),67:(47,'max'),27:(27,'max'),5:(27,'max'),46:(46,'max'),56:(46,'max'),78:(78,'max'),68:(78,'max'),4:(4,'max'),36:(4,'max'),23:(4,'max'),1:(1,'max'),73:(1,'max'),17:(17,'max'),15:(17,'max'),52:(52,'max'),13:(52,'max'),16:(16,'max'),76:(16,'max'),34:(16,'max'),8:(8,'max'),21:(8,'max'),10:(10,'max'),54:(10,'max')}
ZERO_ONLY = (62,26,71,55)

def vehicle_family_sql():
    return 'CASE v.vehicle_id ' + ' '.join(f'WHEN {k} THEN {family}' for k,(family,_) in sorted(FAMILIES.items())) + ' ELSE v.vehicle_id END'

def vehicle_mode_sql():
    return 'CASE v.vehicle_id ' + ' '.join(f"WHEN {k} THEN '{mode}'" for k,(_,mode) in sorted(FAMILIES.items())) + " ELSE 'max' END"

def refresh_soldier_metrics(conn, soldier_id, resource):
    """Refresh only the collected resource within its existing transaction."""
    if resource not in ('weapons', 'vehicles'):
        raise ValueError('unsupported resource')
    process_window(conn, soldier_id, soldier_id + 1, resource=resource)


def process_window(conn, start, stop, resource=None):
    if resource not in (None, "weapons", "vehicles"):
        raise ValueError("unsupported resource")
    params={'start':start,'stop':stop}
    # Acquire per-soldier transaction locks in deterministic ID order. This
    # coordinates window backfills with both live resource success handlers.
    # Lock soldiers (not only existing derived rows): a first collection must
    # not race a backfill that observes no previous metrics.
    for (locked_soldier_id,) in conn.execute(text(
        "SELECT soldier_id FROM soldiers WHERE soldier_id >= :start AND soldier_id < :stop ORDER BY soldier_id"
    ), params):
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('bf4ps:ranking:' || CAST(:sid AS text), 0))"),
                     {"sid": locked_soldier_id})
    if resource in (None, 'weapons'):
        conn.execute(text('DELETE FROM weapon_leaderboard_metrics WHERE soldier_id >= :start AND soldier_id < :stop'),params)
        conn.execute(text('''INSERT INTO weapon_leaderboard_metrics(soldier_id,weapon_id,kills,kpm,accuracy,source_fetched_at)
        SELECT w.soldier_id,w.weapon_id,MAX(w.kills),
        CASE WHEN MAX(w.time_equipped_seconds)>=60 THEN MAX(w.kills)::numeric*60/MAX(w.time_equipped_seconds) END,
        CASE WHEN MAX(w.shots_fired)>=100 AND MAX(w.shots_hit)<=MAX(w.shots_fired)
             THEN MAX(w.shots_hit)::numeric*100/MAX(w.shots_fired) END,
        MAX(w.source_fetched_at)
        FROM soldier_weapon_stats w JOIN collection_state cs ON cs.soldier_id=w.soldier_id
        WHERE w.soldier_id>=:start AND w.soldier_id<:stop AND cs.weapons_state='success'
        GROUP BY w.soldier_id,w.weapon_id'''),params)
    if resource in (None, 'vehicles'):
        conn.execute(text('DELETE FROM vehicle_leaderboard_metrics WHERE soldier_id >= :start AND soldier_id < :stop'),params)
        conn.execute(text(f'''INSERT INTO vehicle_leaderboard_metrics(soldier_id,vehicle_id,kills,kpm,source_fetched_at)
        WITH raw AS (
            SELECT v.soldier_id,{vehicle_family_sql()} AS family_id,{vehicle_mode_sql()} AS mode,
                   MAX(v.kills) AS kills,MAX(v.time_in_seconds) AS seconds,MAX(v.source_fetched_at) AS fetched
            FROM soldier_vehicle_stats v JOIN collection_state cs ON cs.soldier_id=v.soldier_id
            WHERE v.soldier_id>=:start AND v.soldier_id<:stop AND cs.vehicles_state='success'
            GROUP BY v.soldier_id,v.vehicle_id),
        family AS (SELECT soldier_id,family_id,
                  CASE WHEN MAX(mode)='sum' THEN SUM(kills) ELSE MAX(kills) END kills,
                  CASE WHEN MAX(mode)='sum' THEN SUM(seconds) ELSE MAX(seconds) END seconds,
                  MAX(fetched) fetched FROM raw GROUP BY soldier_id,family_id)
        SELECT soldier_id,family_id,kills,
               CASE WHEN seconds>=60 THEN kills::numeric*60/seconds END,fetched FROM family'''),params)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--batch-size',type=int,default=500)
    parser.add_argument('--start-id',type=int,default=0)
    parser.add_argument('--max-batches',type=int,default=1)
    parser.add_argument('--allow-production',action='store_true')
    args=parser.parse_args()
    if not 1<=args.batch_size<=5000 or args.start_id<0 or not 1<=args.max_batches<=10000:
        parser.error('invalid bounds')
    url=os.environ['BF4PS_DATABASE_URL']; parsed=make_url(url)
    if parsed.database!='bf4ps_ranking_scratch' and not (args.allow_production and parsed.database=='bf4_playerstats'):
        parser.error('REFUSING: explicit scratch database or --allow-production required')
    engine=create_engine(url)
    with engine.connect() as c:
        actual=c.execute(text('SELECT current_database()')).scalar_one()
        revision=c.execute(text('SELECT version_num FROM alembic_version')).scalar_one()
        if actual!=parsed.database or revision!='0013_indexed_equipment_rankings':
            parser.error(f'REFUSING: unexpected database/revision: {actual}/{revision}')
        end=c.execute(text('SELECT COALESCE(MAX(soldier_id),0)+1 FROM soldiers')).scalar_one()
    for i in range(args.max_batches):
        start=args.start_id+i*args.batch_size
        if start>=end:break
        stop=min(start+args.batch_size,end)
        with engine.begin() as conn:
            process_window(conn,start,stop)
        print(f'COMMITTED [{start},{stop}); resume with --start-id {stop}',flush=True)
    print('Finished bounded invocation; no external requests')

if __name__=='__main__':main()
