"""Run one explicitly approved, fenced compact scope; never discover jobs."""
import argparse
import os
import signal
import socket
import subprocess
import sys
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from bf4ps.distributed_rank_queue import register, renew, finish
from bf4ps.scoped_rank_claim import claim_scope


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--kind', required=True, choices=('weapon','vehicle'))
    p.add_argument('--item', type=int, required=True)
    p.add_argument('--platform', required=True, choices=('pc','ps4','xboxone','all'))
    p.add_argument('--metric', required=True, choices=('kills','kpm','accuracy'))
    p.add_argument('--production-ack', action='store_true')
    a = p.parse_args()
    if a.item < 1 or (a.kind == 'vehicle' and a.metric == 'accuracy'):
        p.error('invalid scope')
    scope = f'{a.kind}:{a.item}:{a.platform}:{a.metric}'
    url = os.environ['BF4PS_DATABASE_URL']
    db = make_url(url).database
    if db not in ('bf4_playerstats','bf4ps_ranking_scratch','bf4ps_ranking_real_parity'):
        p.error('unexpected database')
    if db == 'bf4_playerstats' and (not a.production_ack or os.getenv('BF4PS_COMPACT_PRODUCTION_SCOPE') != scope):
        p.error('production requires exact scope authorization and --production-ack')
    if db != 'bf4_playerstats' and a.production_ack:
        p.error('production acknowledgement only valid in production')
    engine = create_engine(url,pool_pre_ping=True)
    with engine.connect() as c:
        revision = c.execute(text('SELECT version_num FROM alembic_version')).scalar_one()
        if revision not in ('0023_compact_exclusion_guard', '0024_profile_lookup_idx'):
            raise RuntimeError(f'expected migration 0023, got {revision}')
    worker = register(engine, socket.gethostname(), os.getenv('BF4PS_SITE'))
    job = claim_scope(engine,worker,a.kind,a.item,a.platform,a.metric)
    if job is None:
        raise RuntimeError('scope unavailable, at capacity, or replication gate closed')
    cmd = [sys.executable,str(Path(__file__).with_name('build_compact_rank.py')),
           '--kind',a.kind,'--item',str(a.item),'--platform',a.platform,
           '--metric',a.metric,'--snapshot-format','2','--publish',
           '--rank-worker-id',str(worker),'--rank-claim-token',str(job['token']),
           '--rank-claim-epoch',str(job['epoch'])]
    if db == 'bf4_playerstats':
        cmd.append('--production-ack')
    process = subprocess.Popen(cmd,env=os.environ.copy())
    lost = False
    try:
        while True:
            try:
                rc = process.wait(timeout=10)
                break
            except subprocess.TimeoutExpired:
                if not renew(engine,job):
                    lost = True
                    process.terminate()
                    try: process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                    break
        if lost:
            raise RuntimeError('claim lost; publication must be rejected')
        if not finish(engine,job,rc == 0,None if rc == 0 else f'exit {rc}',refresh_seconds=15):
            raise RuntimeError('claim expired before finish')
        if rc != 0:
            raise RuntimeError(f'compact builder exited {rc}')
        print(f'completed one compact scope: {scope}',flush=True)
    finally:
        if process.poll() is None:
            process.terminate()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: process.kill(); process.wait()
        engine.dispose()

if __name__ == '__main__':
    main()
