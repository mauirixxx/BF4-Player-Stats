"""Explicit, single-scope general ranking cycle runner.

No daemon, timer, service, or automatic activation. Dry-run by default.
The oldest published scope is refreshed first; missing scopes precede published
ones. Publication uses the publisher's transaction advisory lock.
"""
import argparse
import os
from sqlalchemy import create_engine, text
from bf4ps.general_rank_publisher import METRICS, PLATFORMS, build_scope

def select_next_scope(conn):
    revision = conn.execute(text('SELECT version_num FROM alembic_version')).scalar_one()
    if revision != '0026_general_rank_snapshots':
        raise RuntimeError(f'Expected Alembic 0026, found {revision}')
    published = {(r.metric, r.platform): r.published_at for r in
                 conn.execute(text('SELECT metric,platform,published_at FROM general_rank_published'))}
    # Stable tie-breaker ensures predictable bootstrap and avoids random churn.
    return min(((m,p) for m in METRICS for p in PLATFORMS),
               key=lambda scope: (published.get(scope) is not None,
                                  published.get(scope).isoformat() if published.get(scope) else '',
                                  METRICS.index(scope[0]), PLATFORMS.index(scope[1])))

def run_once(engine, execute=False):
    if not execute:
        with engine.connect() as conn:
            scope=select_next_scope(conn)
        return {'scope':scope,'executed':False}
    # Acquire shared publisher/retention lock BEFORE choosing the next scope,
    # so competing schedulers cannot choose the same stale candidate.
    with engine.begin() as conn:
        conn.execute(text('SELECT pg_advisory_xact_lock(640041,260026)'))
        scope=select_next_scope(conn)
        generation,population=build_scope(conn,*scope)
    return {'scope':scope,'executed':True,
            'generation':generation,'population':population}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute',action='store_true',
                        help='Publish exactly one scope; otherwise dry-run')
    args=parser.parse_args()
    engine=create_engine(os.environ['BF4PS_DATABASE_URL'],pool_pre_ping=True)
    try:
        result=run_once(engine,execute=args.execute)
        print(result)
    finally:
        engine.dispose()

if __name__=='__main__':
    main()
