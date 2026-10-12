"""D3-only, HTTP-free endurance harness. See docs/stage9c-d3-900-job-endurance-design.md."""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import quantiles
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from bf4ps.collection_jobs import claim_next_job, release_for_retry

DB = 'bf4ps_scratch_stage9c_d3'
USER = 'bf4ps_stage9c_d2'
REVISION = '0006_stage9c_soak_round_ledger'
SITES = ('tcou', 'kah-01', 'hnl-01')
EVIDENCE = Path('/root/bf4ps-d3-evidence')


def checked_url(environ):
    a, b = environ.get('BF4PS_DATABASE_URL'), environ.get('BF4PS_STAGE9C_D3_URL')
    if not a or a != b or make_url(a).database != DB:
        raise RuntimeError('D3 URL identity mismatch; refusing database access')
    return a


def validate_identity(conn):
    row = conn.execute(text("SELECT current_database(), current_user, pg_is_in_recovery(), current_setting('transaction_read_only')")).one()
    if tuple(row) != (DB, USER, False, 'off'):
        raise RuntimeError('D3 SQL identity mismatch: ' + repr(tuple(row)))
    revision = conn.execute(text('SELECT version_num FROM alembic_version')).scalar_one()
    if revision != REVISION:
        raise RuntimeError('D3 Alembic mismatch: ' + str(revision))


def cohorts(conn):
    rows = conn.execute(text('SELECT soldier_id,current_name FROM soldiers ORDER BY soldier_id')).all()
    result = {site: [] for site in SITES}
    for sid, name in rows:
        matches = [site for site in SITES if name.startswith('D3_SYNTH_' + site + '_') and name[len('D3_SYNTH_' + site + '_'):].isdigit()]
        if len(matches) != 1:
            raise RuntimeError('Non-D3 synthetic soldier: ' + str(name))
        result[matches[0]].append(sid)
    if len(rows) != 900 or any(len(v) != 300 or len(set(v)) != 300 for v in result.values()):
        raise RuntimeError('Expected exactly 300 synthetic soldiers per site')
    return result


def inspect(conn):
    validate_identity(conn)
    site_ids = cohorts(conn)
    rows = conn.execute(text('''SELECT j.job_id,j.soldier_id,j.status,j.attempt_count,j.collector_uuid,
        j.lease_expires_at,j.resource,j.lane,j.reason,c.hostname,c.collector_name
        FROM collection_jobs j LEFT JOIN collectors c ON c.collector_uuid=j.collector_uuid
        ORDER BY j.job_id''')).mappings().all()
    if len(rows) != 900 or len({r['soldier_id'] for r in rows}) != 900:
        raise RuntimeError('Expected exactly 900 unique D3 jobs')
    ownership = {sid: site for site, ids in site_ids.items() for sid in ids}
    errors = []
    for r in rows:
        if r['resource'] != 'detailed' or r['lane'] != 'background' or r['reason'] != 'stage9c_d3_synthetic_postgres_stress':
            errors.append('job metadata mismatch ' + str(r['job_id']))
        if r['collector_uuid'] is not None and r['hostname'] != ownership[r['soldier_id']]:
            errors.append('cross-site ownership job ' + str(r['job_id']))
    statuses = dict(Counter(r['status'] for r in rows))
    collectors = [dict(row) for row in conn.execute(text('SELECT collector_uuid,collector_name,hostname,retired_at FROM collectors ORDER BY collector_name')).mappings()]
    active = conn.execute(text("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND state='active'")).scalar_one()
    total = conn.execute(text('SELECT count(*) FROM pg_stat_activity WHERE datname=current_database()')).scalar_one()
    return {'utc': datetime.now(timezone.utc).isoformat(), 'database': DB, 'cohorts': {k:len(v) for k,v in site_ids.items()},
            'statuses':statuses, 'attempt_sum':sum(r['attempt_count'] for r in rows), 'ownership_errors':errors,
            'collectors':collectors, 'connections':{'active':active,'total':total},
            'jobs':[{'job_id':r['job_id'],'soldier_id':r['soldier_id'],'status':r['status'],
                     'attempt_count':r['attempt_count'],'collector_uuid':r['collector_uuid'],
                     'lease_expires_at':r['lease_expires_at']} for r in rows]}


def write_evidence(name, data):
    EVIDENCE.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = EVIDENCE / name
    with path.open('x') as handle:
        json.dump(data, handle, default=str, indent=2, sort_keys=True)
        handle.write('\n')
        handle.flush()
        os.fsync(handle.fileno())
    path.chmod(0o600)
    return str(path)


def preflight(conn):
    report = inspect(conn)
    if report['ownership_errors']:
        raise RuntimeError('D3 ownership invariant violated: ' + repr(report['ownership_errors']))
    return report


def reset(conn, *, execute, evidence_path):
    report = preflight(conn)
    if not execute:
        return {'dry_run':True, 'statuses':report['statuses'], 'collectors':len(report['collectors'])}
    if not evidence_path or not Path(evidence_path).is_file():
        raise RuntimeError('Pre-reset evidence file required')
    saved = json.loads(Path(evidence_path).read_text())
    if saved.get('database') != DB or saved.get('jobs') != report['jobs'] or saved.get('collectors') != report['collectors']:
        raise RuntimeError('Pre-reset evidence does not match current database state')
    if not conn.execute(text('SELECT pg_try_advisory_xact_lock(943900)')).scalar_one():
        raise RuntimeError('D3 worker active; refusing reset')
    if any(not str(c['collector_name']).startswith('D3_') for c in report['collectors']):
        raise RuntimeError('Unexpected collector: refusing reset')
    # Never reset while test collectors hold open sessions, even when leases have expired.
    other_sessions = conn.execute(text("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid()" )).scalar_one()
    if other_sessions:
        raise RuntimeError('Other D3 sessions active; refusing reset')
    # Lock all jobs and verify their identity again before mutation.
    locked = conn.execute(text('SELECT job_id FROM collection_jobs ORDER BY job_id FOR UPDATE')).scalars().all()
    if len(locked) != 900:
        raise RuntimeError('Queue changed during reset')
    conn.execute(text('''UPDATE collection_jobs SET status='pending',attempt_count=0,collector_uuid=NULL,
        lease_token=NULL,claimed_at=NULL,started_at=NULL,lease_expires_at=NULL,eligible_at=now(),updated_at=now()'''))
    conn.execute(text("DELETE FROM collectors WHERE collector_name LIKE 'D3_%'"))
    return {'reset':900, 'deleted_collectors':len(report['collectors'])}


def worker(engine, *, site, seconds, max_cycles, run_id):
    if site not in SITES or socket.gethostname().split('.')[0] != site:
        raise RuntimeError('Site must match physical hostname')
    with engine.connect() as conn:
        report = preflight(conn)
        ids = cohorts(conn)[site]
        conn.rollback()
    # Hold a session-level lock for the entire worker lifetime; reset takes the
    # corresponding exclusive transaction lock and fails closed on contention.
    guard = engine.connect()
    if not guard.execute(text('SELECT pg_try_advisory_lock_shared(943900)')).scalar_one():
        guard.close()
        raise RuntimeError('D3 reset in progress')
    guard.commit()
    collector_name = 'D3_ENDURANCE_' + site + '_' + run_id
    with engine.begin() as conn:
        uid = conn.execute(text('''INSERT INTO collectors(collector_name,hostname,lane,egress_key)
             VALUES (:name,:site,'background',:egress) RETURNING collector_uuid'''),
             {'name':collector_name,'site':site,'egress':'d3-endurance-'+site}).scalar_one()
    stats = Counter()
    latencies = []
    deadline = time.monotonic() + seconds
    try:
        while time.monotonic() < deadline and (max_cycles is None or stats['cycles'] < max_cycles):
            start = time.monotonic()
            with engine.begin() as conn:
                job = claim_next_job(conn,collector_uuid=uid,allowed_soldier_ids=ids,lease_seconds=60)
                if job is not None and job.soldier_id not in ids:
                    raise RuntimeError('Cross-site claim')
            if job is None:
                stats['empty_polls'] += 1
                time.sleep(0.25)
                continue
            stats['claims'] += 1
            with engine.begin() as conn:
                if not release_for_retry(conn,job,retry_after_seconds=0):
                    raise RuntimeError('Lease token rejected on release')
            stats['releases'] += 1
            stats['cycles'] += 1
            latencies.append((time.monotonic()-start)*1000)
    finally:
        output = {'run_id':run_id,'site':site,'collector_uuid':str(uid),'utc':datetime.now(timezone.utc).isoformat(),
                  'stats':dict(stats),'latency_ms':{'min':min(latencies) if latencies else None,
                  'max':max(latencies) if latencies else None,'mean':sum(latencies)/len(latencies) if latencies else None}}
        try:
            print(json.dumps({'evidence':write_evidence('worker-'+run_id+'-'+site+'.json',output),**output},default=str),flush=True)
        finally:
            guard.execute(text('SELECT pg_advisory_unlock_shared(943900)'))
            guard.close()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='action',required=True)
    for action in ('preflight','snapshot','verify','reset','worker'):
        cmd=sub.add_parser(action)
        if action=='reset':
            cmd.add_argument('--execute',action='store_true')
            cmd.add_argument('--evidence-path')
        if action=='worker':
            cmd.add_argument('--site',required=True,choices=SITES)
            cmd.add_argument('--seconds',type=int,default=60)
            cmd.add_argument('--max-cycles',type=int)
            cmd.add_argument('--run-id',default=None)
    args=p.parse_args()
    url=checked_url(os.environ)
    engine=create_engine(url,pool_size=2,max_overflow=0,pool_timeout=10,connect_args={'connect_timeout':10})
    try:
        if args.action=='worker':
            if not 1<=args.seconds<=14400 or (args.max_cycles is not None and args.max_cycles<1):
                raise ValueError('Invalid worker duration or cycle limit')
            worker(engine,site=args.site,seconds=args.seconds,max_cycles=args.max_cycles,run_id=args.run_id or uuid4().hex)
            return
        with engine.connect() as conn:
            report=preflight(conn)
            if args.action=='reset':
                result=reset(conn,execute=args.execute,evidence_path=args.evidence_path)
                if args.execute:conn.commit()
                else:conn.rollback()
                print(json.dumps(result,default=str))
            elif args.action=='snapshot':
                path=write_evidence('snapshot-'+uuid4().hex+'.json',report)
                print(json.dumps({'path':path,'jobs':len(report['jobs']),'statuses':report['statuses']}))
            elif args.action=='verify':
                print(json.dumps({'passed':not report['ownership_errors'],'statuses':report['statuses'],
                    'attempt_sum':report['attempt_sum'],'ownership_errors':report['ownership_errors']},default=str))
            else:
                print(json.dumps({'passed':True,'statuses':report['statuses'],
                    'cohorts':report['cohorts'],'connections':report['connections']},default=str))
    finally:engine.dispose()


if __name__=='__main__':
    main()

