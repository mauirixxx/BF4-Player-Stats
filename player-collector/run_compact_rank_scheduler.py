"""Single-process compact ranking scheduler using existing fenced one-scope runner.

One publication per cycle. Existing database WAL gate must clear before next.
The writer never bypasses the gate, claims, or production scope acknowledgement.
"""
import argparse
import os
import subprocess
import sys
import time
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
ORDER BY CASE WHEN j.kind='vehicle' AND j.item_id=10 THEN 0 ELSE 1 END,
 CASE WHEN g.snapshot_format=2 THEN 1 ELSE 0 END,
 CASE WHEN j.platform='all' THEN 0 ELSE 1 END,
 j.next_due_at,j.kind,j.item_id,j.platform,j.metric
LIMIT 1
""")

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--max-publications',type=int,default=1)
    ap.add_argument('--poll-seconds',type=int,default=30)
    ap.add_argument('--production-ack',action='store_true')
    args=ap.parse_args()
    if args.max_publications<1 or args.poll_seconds<5: ap.error('invalid bounds')
    url=os.environ['BF4PS_DATABASE_URL']
    if make_url(url).database!='bf4_playerstats' or not args.production_ack:
        ap.error('requires explicit production acknowledgement and production DB')
    engine=create_engine(url,pool_pre_ping=True)
    count=0
    try:
        with engine.connect() as c:
            revision=c.execute(text('SELECT version_num FROM alembic_version')).scalar_one()
            capacity=c.execute(text('SELECT max_active_builds FROM equipment_rank_capacity WHERE id=1')).scalar_one()
        if revision!='0023_compact_exclusion_guard' or capacity!=1:
            raise RuntimeError('production revision/capacity mismatch')
        while count<args.max_publications:
            with engine.connect() as c:
                ready=c.execute(text('SELECT public.bf4ps_rank_gate_ready()')).scalar_one()
                scope=c.execute(PICK).mappings().first() if ready else None
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
            print('starting compact scope',scope_id,flush=True)
            rc=subprocess.call(cmd,env=env)
            if rc==0:
                count+=1
                print('published',scope_id,'count',count,flush=True)
            else:
                print('scope failed',scope_id,'exit',rc,'cooldown',args.poll_seconds,flush=True)
                time.sleep(args.poll_seconds)
    finally:
        engine.dispose()

if __name__=='__main__':
    main()
