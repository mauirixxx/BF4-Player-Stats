"""Opt-in bounded general-rank retention; no timer, no implicit execution.

Deletes at most one completed, unpublished generation per invocation. The
currently published generation is protected by its FK and an explicit check;
the immediately preceding generation for each scope is also retained.
A minimum age protects recent readers and provides a rollback window.
"""
import argparse
import os
from sqlalchemy import create_engine, text

LOCK_A, LOCK_B = 640041, 260026

def prune_one(conn, min_age_minutes=60):
    if min_age_minutes < 60:
        raise ValueError('Retention grace must be at least 60 minutes')
    conn.execute(text('SELECT pg_advisory_xact_lock(:a,:b)'), {'a':LOCK_A,'b':LOCK_B})
    revision=conn.execute(text('SELECT version_num FROM alembic_version')).scalar_one()
    if revision!='0026_general_rank_snapshots':
        raise RuntimeError(f'Expected Alembic 0026, found {revision}')
    # Keep latest two completed generations per metric/platform, even if the
    # older one is unpublished. Incomplete generations are not touched.
    candidate=conn.execute(text("""
        WITH ordered AS (
          SELECT g.generation_id, g.metric, g.platform, g.completed_at,
                 row_number() OVER (
                   PARTITION BY g.metric,g.platform
                   ORDER BY g.completed_at DESC,g.generation_id DESC
                 ) AS newest_rank
          FROM general_rank_generations g
          WHERE g.completed_at IS NOT NULL
        )
        SELECT o.generation_id
        FROM ordered o
        WHERE o.newest_rank > 2
          AND o.completed_at < now() - (:minutes * interval '1 minute')
          AND NOT EXISTS (
            SELECT 1 FROM general_rank_published p
            WHERE p.generation_id=o.generation_id
          )
        ORDER BY o.completed_at,o.generation_id
        LIMIT 1
    """),{'minutes':min_age_minutes}).scalar_one_or_none()
    if candidate is None:
        return None
    deleted=conn.execute(text("""
        DELETE FROM general_rank_generations g
        WHERE g.generation_id=:generation_id
          AND NOT EXISTS (
            SELECT 1 FROM general_rank_published p
            WHERE p.generation_id=g.generation_id
          )
        RETURNING g.generation_id
    """),{'generation_id':candidate}).scalar_one_or_none()
    if deleted != candidate:
        raise RuntimeError('Retention candidate changed before deletion')
    return deleted

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--min-age-minutes',type=int,default=60)
    args=parser.parse_args()
    if not args.execute:
        parser.error('No writes performed; pass --execute to delete at most one generation')
    engine=create_engine(os.environ['BF4PS_DATABASE_URL'],pool_pre_ping=True)
    try:
        with engine.begin() as conn:
            deleted=prune_one(conn,args.min_age_minutes)
        print(f'General ranking retention: deleted_generation={deleted}')
    finally:
        engine.dispose()

if __name__=='__main__':
    main()
