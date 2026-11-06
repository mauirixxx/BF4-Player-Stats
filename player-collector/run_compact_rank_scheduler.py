"""Single-process compact ranking scheduler using existing fenced one-scope runner.

One publication per cycle. Existing database WAL gate must clear before next.
The writer never bypasses the gate, claims, or production scope acknowledgement.
"""
import argparse
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

PICK = text("""
SELECT j.kind,j.item_id,j.platform,j.metric
FROM equipment_rank_jobs j
LEFT JOIN equipment_rank_compact_published p
 ON p.kind=j.kind AND p.item_id=j.item_id AND p.platform=j.platform AND p.metric=j.metric
LEFT JOIN equipment_rank_generations g ON g.generation_id=p.generation_id
WHERE j.next_due_at<=clock_timestamp()
 AND (j.lease_expires_at IS NULL OR j.lease_expires_at<=clock_timestamp())
 AND ((:shard_count > 0 AND mod(j.item_id, :shard_count) = :shard_index)
      OR (:shard_count = 0 AND (:parity = 'all' OR mod(j.item_id, 2) = CASE WHEN :parity = 'odd' THEN 1 ELSE 0 END)))
ORDER BY CASE WHEN g.snapshot_format=2 THEN 1 ELSE 0 END,
 p.published_at ASC NULLS FIRST,
 j.next_due_at ASC,
 j.kind,j.item_id,j.platform,j.metric
LIMIT 1
""")

SCOPE_COHORT = text("""SELECT kind,item_id,platform,metric FROM equipment_rank_jobs
WHERE ((:shard_count>0 AND mod(item_id,:shard_count)=:shard_index)
 OR (:shard_count=0 AND (:parity='all' OR mod(item_id,2)=CASE WHEN :parity='odd' THEN 1 ELSE 0 END)))""")
def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')
def scope_key(row):
    return (row['kind'],row['item_id'],row['platform'],row['metric'])
def start_sweep(engine,args,number):
    with engine.connect() as c:
        rows=c.execute(SCOPE_COHORT,{'shard_count':args.shard_count,'shard_index':args.shard_index,'parity':args.parity}).mappings().all()
    cohort={scope_key(r) for r in rows}
    print(f'SWEEP STARTED number={number} shard={args.shard_index}/{args.shard_count} assigned={len(cohort)} utc={utc_now()}',flush=True)
    return cohort,set(),time.monotonic()
def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--max-publications',type=int,default=1)
    ap.add_argument('--poll-seconds',type=int,default=30)
    ap.add_argument('--production-ack',action='store_true')
    ap.add_argument('--parity',choices=('all','odd','even'),default=os.environ.get('BF4PS_COMPACT_SCOPE_PARITY','all'))
    ap.add_argument('--shard-count',type=int,default=int(os.environ.get('BF4PS_COMPACT_SHARD_COUNT','0')))
    ap.add_argument('--shard-index',type=int,default=int(os.environ.get('BF4PS_COMPACT_SHARD_INDEX','0')))
    args=ap.parse_args()
    if args.shard_count < 0 or (args.shard_count and not 0 <= args.shard_index < args.shard_count):
        ap.error('shard index must be within [0, shard count); count 0 selects legacy parity')
    if args.max_publications<1 or args.poll_seconds<5 or args.parity not in ('all','odd','even'): ap.error('invalid bounds')
    url=os.environ['BF4PS_DATABASE_URL']
    if make_url(url).database!='bf4_playerstats' or not args.production_ack:
        ap.error('requires explicit production acknowledgement and production DB')
    engine=create_engine(url,pool_pre_ping=True)
    count=0
    try:
        with engine.connect() as c:
            revision=c.execute(text('SELECT version_num FROM alembic_version')).scalar_one()
            capacity=c.execute(text('SELECT max_active_builds FROM equipment_rank_capacity WHERE id=1')).scalar_one()
        if revision not in ('0023_compact_exclusion_guard', '0024_profile_lookup_idx', '0025_compact_lookup_fk_idx') or not 1 <= capacity <= 16:
            raise RuntimeError('production revision/capacity mismatch')
        sweep_number=1
        cohort,completed,sweep_start=start_sweep(engine,args,sweep_number)
        while count<args.max_publications:
            with engine.connect() as c:
                ready=c.execute(text('SELECT public.bf4ps_rank_gate_ready()')).scalar_one()
                priority_file=Path('/rank/priority-scope.txt')
                priority=priority_file.read_text().strip().split(':') if priority_file.exists() else []
                if len(priority)!=4 or priority[0] not in ('weapon','vehicle') or not priority[1].isdecimal() or priority[2] not in ('pc','ps4','xboxone','all') or priority[3] not in ('kills','kpm','accuracy'):
                    priority=['', '0', '', '']
                pick_params={'parity':args.parity,'shard_count':args.shard_count,'shard_index':args.shard_index,'priority_kind':priority[0],
                             'priority_item':int(priority[1]),'priority_platform':priority[2],
                             'priority_metric':priority[3]}
                scope=c.execute(PICK,pick_params).mappings().first() if ready else None
            if not scope:
                print('waiting for WAL replay gate or due scope',flush=True)
                time.sleep(args.poll_seconds)
                continue
            scope=dict(scope)
            scope_id=f"{scope['kind']}:{scope['item_id']}:{scope['platform']}:{scope['metric']}"
            env=os.environ.copy()
            env['BF4PS_COMPACT_PRODUCTION_SCOPE']=scope_id
            cmd=[sys.executable,str(Path(__file__).with_name('run_one_compact_scope.py')),
                 '--kind',scope['kind'],'--item',str(scope['item_id']),
                 '--platform',scope['platform'],'--metric',scope['metric'],'--production-ack']
            print('starting compact scope',scope_id,'parity',args.parity,flush=True)
            rc=subprocess.call(cmd,env=env)
            if rc==0:
                count+=1
                print('published',scope_id,'count',count,flush=True)
                key=scope_key(scope)
                if key in cohort and key not in completed:
                    completed.add(key)
                    total=len(cohort)
                    print(f'SWEEP PROGRESS number={sweep_number} completed={len(completed)}/{total} percent={100*len(completed)/total:.1f} elapsed_seconds={time.monotonic()-sweep_start:.1f}',flush=True)
                    if len(completed)==total:
                        elapsed=time.monotonic()-sweep_start
                        print(f'SWEEP COMPLETE number={sweep_number} completed={total}/{total} duration_seconds={elapsed:.1f} utc={utc_now()}',flush=True)
                        sweep_number+=1
                        cohort,completed,sweep_start=start_sweep(engine,args,sweep_number)
            else:
                print('scope failed',scope_id,'exit',rc,'cooldown',args.poll_seconds,flush=True)
                time.sleep(args.poll_seconds)
    finally:
        engine.dispose()

if __name__=='__main__':
    main()
