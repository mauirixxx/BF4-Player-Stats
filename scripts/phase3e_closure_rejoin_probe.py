#!/usr/bin/env python3
"""Phase 3E closure: prove explicit undrain permits safe stable-identity rejoin.

Run on hnl-01 after the operator explicitly undrains phase3e-hnl-01.
Uses production registration/heartbeat controls, but intentionally claims no
queue work and makes no Battlelog request. Finishes with a clean stop marker.
"""
from __future__ import annotations
import os,socket,sys
from pathlib import Path
from urllib.parse import urlsplit
from sqlalchemy import create_engine,text
sys.path.insert(0,str(Path(__file__).resolve().parent))
from phase3e_lifecycle_a_common import *
from bf4ps.collector_runtime import register_collector,heartbeat_collector,stop_collector
from bf4ps.detailed_collector import CollectorIdentity

SOFTWARE='phase3e-closure-undrain-rejoin'

def main()->int:
    host=socket.gethostname().split('.',1)[0]
    if host!=TARGET_HOST: raise SystemExit(f'REFUSING: must run on {TARGET_HOST}, got {host}')
    frozen=HOSTS[host]
    url=os.environ.get('BF4PS_DATABASE_URL'); p=urlsplit(url or '')
    if not url or p.hostname!=EXPECTED_DB_HOST or p.path.lstrip('/')!=EXPECTED_DATABASE:
        raise SystemExit('REFUSING: wrong database target')
    e=create_engine(url,pool_pre_ping=True)
    ident=CollectorIdentity(frozen.collector_uuid,frozen.collector_name,host,frozen.egress_key,'background')
    with e.begin() as c:
        assert_target(c)
        before=c.execute(text("""SELECT collector_uuid,collector_name,hostname,lane,egress_key,
            enabled,drained,current_job_id,retired_at FROM collectors
            WHERE collector_uuid=:u FOR UPDATE"""),{'u':frozen.collector_uuid}).mappings().one()
        if before['collector_name']!=frozen.collector_name or before['hostname']!=host or before['lane']!='background' or before['egress_key']!=frozen.egress_key or before['retired_at'] is not None:
            raise RuntimeError(f'identity boundary failed: {dict(before)}')
        if not before['enabled'] or before['drained']:
            raise RuntimeError(f'operator must explicitly undrain enabled collector before rejoin probe: enabled={before["enabled"]} drained={before["drained"]}')
        if before['current_job_id'] is not None:
            raise RuntimeError(f'collector still owns job {before["current_job_id"]}')
        control=register_collector(c,identity=ident,software_version=SOFTWARE)
        after_register=c.execute(text("SELECT enabled,drained,current_job_id,software_version FROM collectors WHERE collector_uuid=:u"),{'u':frozen.collector_uuid}).mappings().one()
        hb=heartbeat_collector(c,collector_uuid=frozen.collector_uuid,software_version=SOFTWARE)
        after_hb=c.execute(text("SELECT enabled,drained,current_job_id,heartbeat_state FROM collectors WHERE collector_uuid=:u"),{'u':frozen.collector_uuid}).mappings().one()
        stopped=stop_collector(c,collector_uuid=frozen.collector_uuid)
        final=c.execute(text("SELECT enabled,drained,current_job_id,heartbeat_state FROM collectors WHERE collector_uuid=:u"),{'u':frozen.collector_uuid}).mappings().one()
    checks={
        'explicit operator undrain present': not bool(before['drained']),
        'stable identity registration accepted': True,
        'registration preserved drained=false': not control.drained and not bool(after_register['drained']),
        'registration became claim-eligible': control.may_claim,
        'heartbeat preserved drained=false': not hb.drained and not bool(after_hb['drained']),
        'heartbeat remained claim-eligible': hb.may_claim,
        'rejoin probe acquired no current_job_id': after_register['current_job_id'] is None and after_hb['current_job_id'] is None,
        'clean stop marker succeeded': stopped and final['heartbeat_state']=='unknown',
        'clean stop preserved operator undrain': not bool(final['drained']),
        'clean stop left no current job': final['current_job_id'] is None,
    }
    print('===== BF4PS PHASE 3E UNDRAIN-REJOIN CLOSURE PROBE =====')
    print(f'host: {host}')
    print(f'collector: {frozen.collector_name} {frozen.collector_uuid}')
    for label,ok in checks.items(): print(f'{label:<50} {"PASS" if ok else "FAIL"}')
    print('queue claims: 0')
    print('Battlelog requests: 0')
    print('final drained: False')
    ok=all(checks.values())
    print(f'UNDRAIN-REJOIN CLOSURE: {"PASS" if ok else "FAIL"}')
    return 0 if ok else 1

if __name__=='__main__': raise SystemExit(main())
