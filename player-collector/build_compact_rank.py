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
from bf4ps.compact_exclusions import exclusion_fingerprint


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
    parser.add_argument('--snapshot-format', type=int, choices=(1,2), default=1)
    parser.add_argument('--rank-worker-id')
    parser.add_argument('--rank-claim-token')
    parser.add_argument('--rank-claim-epoch', type=int)
    args = parser.parse_args()
    if args.item < 1 or (args.kind == 'vehicle' and args.metric == 'accuracy'):
        parser.error('invalid item/metric')
    url = os.environ['BF4PS_DATABASE_URL']
    db = make_url(url).database
    if db not in ('bf4ps_ranking_scratch', 'bf4ps_ranking_real_parity', 'bf4_playerstats'):
        parser.error('unexpected database')
    if args.publish and not all(v is not None for v in (args.rank_worker_id,args.rank_claim_token,args.rank_claim_epoch)):
        parser.error('publication requires worker id, claim token and claim epoch')
    if args.publish and db not in ('bf4ps_ranking_scratch', 'bf4ps_ranking_real_parity'):
        parser.error('production publication disabled until fenced writer validation')
    if any(v is not None for v in (args.rank_worker_id,args.rank_claim_token,args.rank_claim_epoch)) and not all(v is not None for v in (args.rank_worker_id,args.rank_claim_token,args.rank_claim_epoch)):
        parser.error('claim fencing requires worker id, token and epoch together')
    # Keep the audited family map synchronized with website/api/leaderboard_api.py.
    # The parity test checks the mappings independently of database availability.
    VEHICLE_FAMILIES = {
        2:(2,'sum'),30:(2,'sum'),41:(41,'sum'),63:(41,'sum'),
        47:(47,'max'),67:(47,'max'),27:(27,'max'),5:(27,'max'),
        46:(46,'max'),56:(46,'max'),78:(78,'max'),68:(78,'max'),
        4:(4,'max'),36:(4,'max'),23:(4,'max'),1:(1,'max'),73:(1,'max'),
        17:(17,'max'),15:(17,'max'),52:(52,'max'),13:(52,'max'),
        16:(16,'max'),76:(16,'max'),34:(16,'max'),8:(8,'max'),
        21:(8,'max'),10:(10,'max'),54:(10,'max'),
    }
    params = vars(args).copy()
    if args.kind == 'vehicle':
        params['item'] = VEHICLE_FAMILIES.get(args.item, (args.item, None))[0]
        raw_ids = sorted({raw for raw, (canonical, _) in VEHICLE_FAMILIES.items()
                          if canonical == params['item']} | {params['item']})
        params['raw_ids'] = raw_ids
        sum_ids = sorted(raw for raw, (_, mode) in VEHICLE_FAMILIES.items() if mode == 'sum')
        source = f'''WITH raw_per_soldier AS (
          SELECT s.soldier_id,t.vehicle_id,max(t.kills) AS kills,
                 max(t.time_in_seconds) AS usage_seconds,
                 max(t.source_fetched_at) AS source_fetched_at
          FROM soldier_vehicle_stats t JOIN soldiers s ON s.soldier_id=t.soldier_id
          JOIN collection_state cs ON cs.soldier_id=s.soldier_id
          WHERE t.vehicle_id=ANY(:raw_ids) AND cs.vehicles_state='success'
            AND (:platform='all' OR s.platform=:platform)
            AND NOT EXISTS (SELECT 1 FROM public.player_exclusions pe
              WHERE pe.platform=s.platform AND pe.persona_id=s.persona_id AND pe.active)
          GROUP BY s.soldier_id,t.vehicle_id
        ), variants AS (
          SELECT soldier_id,
            CASE vehicle_id {' '.join(f'WHEN {raw} THEN {canonical}' for raw,(canonical,_) in VEHICLE_FAMILIES.items())} ELSE vehicle_id END AS item_id,
            CASE WHEN vehicle_id IN ({','.join(map(str,sum_ids))}) THEN 'sum' ELSE 'max' END AS mode,
            kills,usage_seconds,source_fetched_at FROM raw_per_soldier
        ), consolidated AS (
          SELECT soldier_id,item_id,
            CASE WHEN max(mode)='sum' THEN sum(kills) ELSE max(kills) END AS kills,
            CASE WHEN max(mode)='sum' THEN sum(usage_seconds) ELSE max(usage_seconds) END AS usage_seconds,
            max(source_fetched_at) AS source_fetched_at
          FROM variants GROUP BY soldier_id,item_id
        )
        SELECT soldier_id,kills,
          CASE WHEN usage_seconds>=60 THEN kills::numeric*60/usage_seconds END AS kpm,
          NULL::numeric AS accuracy,source_fetched_at
        FROM consolidated WHERE item_id=:item'''
    else:
        source = '''SELECT s.soldier_id,max(t.kills) AS kills,
          CASE WHEN max(t.time_equipped_seconds)>=60
            THEN max(t.kills)::numeric*60/max(t.time_equipped_seconds) END AS kpm,
          CASE WHEN max(t.shots_fired)>=100 AND max(t.shots_hit)<=max(t.shots_fired)
            THEN max(t.shots_hit)::numeric*100/max(t.shots_fired) END AS accuracy,
          max(t.source_fetched_at) AS source_fetched_at
          FROM soldier_weapon_stats t JOIN soldiers s ON s.soldier_id=t.soldier_id
          JOIN collection_state cs ON cs.soldier_id=s.soldier_id
          WHERE t.weapon_id=:item AND cs.weapons_state='success'
            AND (:platform='all' OR s.platform=:platform)
            AND NOT EXISTS (SELECT 1 FROM public.player_exclusions pe
              WHERE pe.platform=s.platform AND pe.persona_id=s.persona_id AND pe.active)
          GROUP BY s.soldier_id'''
    params = {**vars(args), **{k:v for k,v in params.items() if k in ('item','raw_ids')}}
    engine = create_engine(url, pool_pre_ping=True)
    started = time.monotonic()
    with engine.connect().execution_options(isolation_level='REPEATABLE READ') as conn:
        revision = conn.execute(text('SELECT version_num FROM alembic_version')).scalar_one()
        if revision not in ('0020_compact_rank_snapshots', '0021_reconcile_player_exclusions', '0022_compact_blocks_only_format', '0023_compact_exclusion_guard'):
            raise RuntimeError(f'migration 0020 required, found {revision}')
        if args.snapshot_format == 2 and revision != '0023_compact_exclusion_guard':
            raise RuntimeError('safe format-2 publication requires migration 0023')
        conn.execute(text("SET LOCAL statement_timeout='120s'"))
        conn.execute(text("SET LOCAL work_mem='32MB'"))
        scope_version = conn.execute(text('''SELECT version FROM equipment_rank_scope_versions
          WHERE kind=:kind AND item_id=:item AND platform=:platform'''), params).scalar_one_or_none()
        if scope_version is None:
            raise RuntimeError('scope version missing')
        fingerprint = exclusion_fingerprint(conn) if args.snapshot_format == 2 else None
        generation = conn.execute(text('''INSERT INTO equipment_rank_generations
          (kind,item_id,platform,metric,snapshot_format,exclusion_fingerprint)
          VALUES (:kind,:item,:platform,:metric,:format,:fingerprint) RETURNING generation_id'''),
          {**params,'format':args.snapshot_format,'fingerprint':fingerprint}).scalar_one() if revision == '0023_compact_exclusion_guard' else conn.execute(text('''INSERT INTO equipment_rank_generations
          (kind,item_id,platform,metric,snapshot_format)
          VALUES (:kind,:item,:platform,:metric,1) RETURNING generation_id'''),params).scalar_one()
        source = f'SELECT m.soldier_id,m.{args.metric} AS score,m.kills,m.kpm,m.accuracy,m.source_fetched_at FROM ({source}) m'
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
            if args.snapshot_format == 1:
                conn.execute(text('''INSERT INTO equipment_rank_compact_lookup
              (generation_id,soldier_id,block_id,block_offset)
              VALUES (:g,:soldier,:block,:offset)'''),
              [{'g':generation,'soldier':int(r.soldier_id),'block':block_id,'offset':offset}
                   for offset,r in enumerate(batch)])
            for r in batch:
                if r.source_fetched_at is not None and (latest is None or r.source_fetched_at > latest):
                    latest = r.source_fetched_at
            count += len(batch)
        # Legacy eligibility and family consolidation define the population.
        # equipment_population is a separately maintained metric-table count;
        # rejecting a correct legacy cohort against it would be incorrect.
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
        if args.snapshot_format == 2 and exclusion_fingerprint(conn) != fingerprint:
            raise RuntimeError('exclusions changed during build: refusing publication')
        if args.publish:
            job = conn.execute(text('''SELECT 1 FROM equipment_rank_jobs WHERE
              kind=:kind AND item_id=:item AND platform=:platform AND metric=:metric
              AND claimed_by=CAST(:worker AS uuid) AND claim_token=CAST(:token AS uuid)
              AND claim_epoch=:epoch AND lease_expires_at>now() FOR UPDATE'''),
              {**params,'worker':args.rank_worker_id,'token':args.rank_claim_token,'epoch':args.rank_claim_epoch}).first()
            if job is None:
                raise RuntimeError('stale or expired distributed claim: refusing publication')
        conn.execute(text('''INSERT INTO equipment_rank_compact_published
          (kind,item_id,platform,metric,generation_id) VALUES
          (:kind,:item,:platform,:metric,:g)
          ON CONFLICT (kind,item_id,platform,metric) DO UPDATE
          SET generation_id=EXCLUDED.generation_id,published_at=now()'''),{**params,'g':generation})
        conn.execute(text("UPDATE equipment_rank_generations SET status='published' WHERE generation_id=:g"),{'g':generation})
    print(f'PUBLISHED SCRATCH: generation {generation}, {count} rows, {time.monotonic()-started:.2f}s')


if __name__ == '__main__':
    main()
