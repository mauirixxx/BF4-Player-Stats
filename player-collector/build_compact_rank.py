"""Opt-in compact snapshot builder. Never modifies legacy rank rows or pointer.

Requires migration 0020. Default is a rolled-back dry run. A production
publication additionally requires explicit acknowledgement and fencing in a
future release; this candidate intentionally refuses production publishing.
"""
import argparse
import os
import time
from itertools import islice

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from bf4ps.compact_rank_codec import BLOCK_SIZE, encode_block


def chunks(iterator, size):
    while batch := list(islice(iterator, size)):
        yield batch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kind', required=True, choices=('weapon', 'vehicle'))
    parser.add_argument('--item', type=int, required=True)
    parser.add_argument('--platform', required=True, choices=('pc', 'ps4', 'xboxone', 'all'))
    parser.add_argument('--metric', required=True, choices=('kills', 'kpm', 'accuracy'))
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    if args.item < 1 or (args.kind == 'vehicle' and args.metric == 'accuracy'):
        parser.error('invalid item/metric')
    url = os.environ['BF4PS_DATABASE_URL']
    db = make_url(url).database
    if db not in ('bf4ps_ranking_scratch', 'bf4_playerstats'):
        parser.error('unexpected database')
    if args.publish and db != 'bf4ps_ranking_scratch':
        parser.error('production publication disabled until fenced writer validation')
    table = 'weapon_leaderboard_metrics' if args.kind == 'weapon' else 'vehicle_leaderboard_metrics'
    item_column = 'weapon_id' if args.kind == 'weapon' else 'vehicle_id'
    params = vars(args).copy()
    engine = create_engine(url, pool_pre_ping=True)
    started = time.monotonic()
    with engine.connect().execution_options(isolation_level='REPEATABLE READ') as conn:
        revision = conn.execute(text('SELECT version_num FROM alembic_version')).scalar_one()
        if revision != '0020_compact_rank_snapshots':
            raise RuntimeError(f'migration 0020 required, found {revision}')
        conn.execute(text("SET LOCAL statement_timeout='120s'"))
        conn.execute(text("SET LOCAL work_mem='32MB'"))
        scope_version = conn.execute(text('''SELECT version FROM equipment_rank_scope_versions
          WHERE kind=:kind AND item_id=:item AND platform=:platform'''), params).scalar_one_or_none()
        if scope_version is None:
            raise RuntimeError('scope version missing')
        generation = conn.execute(text('''INSERT INTO equipment_rank_generations
          (kind,item_id,platform,metric,snapshot_format)
          VALUES (:kind,:item,:platform,:metric,1) RETURNING generation_id'''), params).scalar_one()
        source = f'''SELECT m.soldier_id,m.{args.metric} AS score,m.kills,m.kpm,
          {'m.accuracy' if args.kind == 'weapon' else 'NULL::numeric'} AS accuracy,
          m.source_fetched_at FROM {table} m
          JOIN soldiers s ON s.soldier_id=m.soldier_id
          WHERE m.{item_column}=:item AND (:platform='all' OR s.platform=:platform)
          AND NOT EXISTS (SELECT 1 FROM player_exclusions x WHERE x.platform=s.platform
            AND x.persona_id=s.persona_id AND x.active)'''
        ranked = text(f'''SELECT soldier_id,kills,kpm,accuracy,source_fetched_at,
          rank() OVER (ORDER BY score DESC NULLS LAST) AS rank,
          row_number() OVER (ORDER BY score DESC NULLS LAST,soldier_id) AS position
          FROM ({source}) eligible ORDER BY position''')
        # Materialize the ranked source before issuing writes on this connection.
        # PostgreSQL server-side cursors cannot safely interleave with inserts
        # through the same connection while their result is still streaming.
        result = conn.execute(ranked, params)
        count = 0
        latest = None
        for block_id, batch in enumerate(chunks(result, BLOCK_SIZE)):
            first = count + 1
            payload = encode_block([(int(r.soldier_id), int(r.rank), r.kills,
                                     r.kpm, r.accuracy, r.source_fetched_at) for r in batch])
            conn.execute(text('''INSERT INTO equipment_rank_compact_blocks
              (generation_id,block_id,first_position,last_position,payload)
              VALUES (:g,:b,:first,:last,:payload)'''),
              {'g':generation,'b':block_id,'first':first,'last':first+len(batch)-1,'payload':payload})
            conn.execute(text('''INSERT INTO equipment_rank_compact_lookup
              (generation_id,soldier_id,block_id,block_offset)
              VALUES (:g,:soldier,:block,:offset)'''),
              [{'g':generation,'soldier':int(r.soldier_id),'block':block_id,'offset':offset}
               for offset,r in enumerate(batch)])
            for r in batch:
                if r.source_fetched_at is not None and (latest is None or r.source_fetched_at > latest):
                    latest = r.source_fetched_at
            count += len(batch)
        expected = conn.execute(text('''SELECT coalesce(sum(population),0) FROM equipment_population
          WHERE kind=:kind AND item_id=:item AND (:platform='all' OR platform=:platform)'''),params).scalar_one()
        if count != expected:
            raise RuntimeError(f'population mismatch: {count} != {expected}')
        conn.execute(text('''UPDATE equipment_rank_generations SET status='validated',
          row_count=:count,input_scope_version=:version,completed_at=now(),
          input_max_fetched_at=:latest WHERE generation_id=:g'''),
          {'count':count,'version':scope_version,'latest':latest,'g':generation})
        if not args.publish:
            conn.rollback()
            print(f'DRY RUN: {count} rows, {time.monotonic()-started:.2f}s, rolled back')
            return
        conn.commit()
    # Scratch only: independent pointer, atomic visibility after all blocks exist.
    with engine.begin() as conn:
        conn.execute(text("SET LOCAL lock_timeout='3s'"))
        current = conn.execute(text('''SELECT version FROM equipment_rank_scope_versions
          WHERE kind=:kind AND item_id=:item AND platform=:platform FOR UPDATE'''),params).scalar_one()
        if current != scope_version:
            raise RuntimeError('scope changed during build: refusing publication')
        conn.execute(text('''INSERT INTO equipment_rank_compact_published
          (kind,item_id,platform,metric,generation_id) VALUES
          (:kind,:item,:platform,:metric,:g)
          ON CONFLICT (kind,item_id,platform,metric) DO UPDATE
          SET generation_id=EXCLUDED.generation_id,published_at=now()'''),{**params,'g':generation})
        conn.execute(text("UPDATE equipment_rank_generations SET status='published' WHERE generation_id=:g"),{'g':generation})
    print(f'PUBLISHED SCRATCH: generation {generation}, {count} rows, {time.monotonic()-started:.2f}s')


if __name__ == '__main__':
    main()
