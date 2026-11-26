"""Opt-in general leaderboard snapshot publisher; never started by collector startup.

Supports Alembic 0026 and 0027. A single transaction builds and publishes one scope;
transaction-scoped advisory lock prevents competing scope publishers. No scheduler
or retention worker is installed by this module.
"""
import argparse
import os
from sqlalchemy import create_engine, text

METRICS = ('kills', 'total_score', 'wins', 'time_played_seconds',
           'conquest_score', 'rush_score', 'team_deathmatch_score',
           'domination_score', 'obliteration_score', 'defuse_score',
           'capture_the_flag_score', 'air_superiority_score',
           'carrier_assault_score', 'chain_link_score')
PLATFORMS = ('all', 'pc', 'ps4', 'xboxone')
CUTS = (3, 8, 15, 25, 35, 50, 65, 80, 90)


def build_scope(conn, metric: str, platform: str) -> tuple[int, int]:
    """Build a complete generation and publish it atomically, or roll back."""
    if metric not in METRICS or platform not in PLATFORMS:
        raise ValueError('Invalid general ranking scope')
    # Lock shared across all publishers, intentionally serializing builds.
    conn.execute(text('SELECT pg_advisory_xact_lock(640041, 260026)'))
    revision = conn.execute(text('SELECT version_num FROM alembic_version')).scalar_one()
    if revision not in ('0026_general_rank_snapshots', '0027_soldier_ban_status'):
        raise RuntimeError(f'Expected Alembic 0026 or 0027, found {revision}')
    # Prevent a new publisher from replacing the same scope mid-build.
    generation = conn.execute(text('''
        INSERT INTO general_rank_generations(metric,platform,population)
        VALUES (:metric,:platform,0) RETURNING generation_id
    '''), {'metric': metric, 'platform': platform}).scalar_one()
    cuts = ' '.join(f'WHEN rank * 100.0 / NULLIF(population,0) <= {cut} THEN {i}'
                    for i, cut in enumerate(CUTS, 1))
    # Only the allowlisted metric is interpolated. Rank before any page filter.
    count = conn.execute(text(f'''
        WITH cohort AS (
          SELECT s.soldier_id, d.{metric} AS value,
                 d.time_played_seconds AS hours_source_seconds
          FROM soldiers s
          JOIN collection_state cs ON cs.soldier_id=s.soldier_id
          JOIN detailed_stats_current d ON d.soldier_id=s.soldier_id
          WHERE cs.detailed_state='success' AND d.{metric} IS NOT NULL
            AND NOT EXISTS (
              SELECT 1 FROM public.player_exclusions pe
              WHERE pe.platform=s.platform AND pe.persona_id=s.persona_id AND pe.active
            )
            AND (:platform='all' OR s.platform=:platform)
        ), ranked AS (
          SELECT *, rank() OVER (ORDER BY value DESC) AS rank,
                 row_number() OVER (ORDER BY value DESC,soldier_id) AS position,
                 count(*) OVER () AS population FROM cohort
        )
        INSERT INTO general_rank_rows
          (generation_id,position,soldier_id,value,rank,division,hours_source_seconds)
        SELECT :generation_id,position,soldier_id,value,rank,
               CASE {cuts} ELSE 10 END,hours_source_seconds
        FROM ranked
    '''), {'platform': platform, 'generation_id': generation}).rowcount
    # PostgreSQL returns affected row count for INSERT ... SELECT.
    if count < 0:
        raise RuntimeError('Unable to verify inserted row count')
    conn.execute(text('''
        UPDATE general_rank_generations
        SET population=:population, completed_at=now()
        WHERE generation_id=:generation_id
    '''), {'population': count, 'generation_id': generation})
    conn.execute(text('''
        INSERT INTO general_rank_published(metric,platform,generation_id,published_at)
        VALUES (:metric,:platform,:generation_id,now())
        ON CONFLICT (metric,platform) DO UPDATE
        SET generation_id=EXCLUDED.generation_id,published_at=EXCLUDED.published_at
    '''), {'metric': metric, 'platform': platform, 'generation_id': generation})
    return generation, count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--metric', required=True, choices=METRICS)
    parser.add_argument('--platform', required=True, choices=PLATFORMS)
    parser.add_argument('--execute', action='store_true', help='Explicitly write a single snapshot')
    args = parser.parse_args()
    if not args.execute:
        parser.error('No writes performed; pass --execute to publish one scope')
    url = os.environ['BF4PS_DATABASE_URL']
    engine = create_engine(url, pool_pre_ping=True)
    try:
        with engine.begin() as conn:
            generation, population = build_scope(conn, args.metric, args.platform)
        print(f'Published {args.metric}/{args.platform}: generation={generation} population={population}')
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
