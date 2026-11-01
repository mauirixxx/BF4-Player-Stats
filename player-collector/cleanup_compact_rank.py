"""Scratch-only compact generation retention; dry-run unless --execute.

Keep all published generations and at least the newest N per scope. Delete
only compact generations with no legacy rows or legacy published references.
"""
import argparse
import os
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--keep', type=int, default=2)
    args = parser.parse_args()
    if args.keep < 2:
        parser.error('--keep must be >= 2')
    url = os.environ['BF4PS_DATABASE_URL']
    if make_url(url).database != 'bf4ps_ranking_scratch':
        parser.error('cleanup restricted to scratch database')
    engine = create_engine(url)
    with engine.begin() as conn:
        if conn.execute(text('SELECT version_num FROM alembic_version')).scalar_one() not in ('0020_compact_rank_snapshots','0021_reconcile_player_exclusions'):
            raise RuntimeError('compact migration required')
        candidates = conn.execute(text('''WITH ordered AS (
          SELECT g.generation_id,
          row_number() OVER (PARTITION BY g.kind,g.item_id,g.platform,g.metric
            ORDER BY g.created_at DESC,g.generation_id DESC) AS recency
          FROM equipment_rank_generations g
          WHERE EXISTS (SELECT 1 FROM equipment_rank_compact_blocks b
                        WHERE b.generation_id=g.generation_id)
        ) SELECT o.generation_id FROM ordered o
          WHERE o.recency>:keep
          AND NOT EXISTS (SELECT 1 FROM equipment_rank_compact_published p WHERE p.generation_id=o.generation_id)
          AND NOT EXISTS (SELECT 1 FROM equipment_rank_published p WHERE p.generation_id=o.generation_id)
          AND NOT EXISTS (SELECT 1 FROM equipment_rank_rows r WHERE r.generation_id=o.generation_id)
          ORDER BY o.generation_id'''),{'keep':args.keep}).scalars().all()
        print(f'eligible for retention cleanup: {len(candidates)} generations')
        if not args.execute or not candidates:
            return
        conn.execute(text('DELETE FROM equipment_rank_generations WHERE generation_id=ANY(:ids)'),{'ids':candidates})
        print(f'deleted {len(candidates)} unreferenced compact generations')


if __name__ == '__main__':
    main()
