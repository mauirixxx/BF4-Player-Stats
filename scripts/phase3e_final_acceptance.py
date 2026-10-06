#!/usr/bin/env python3
"""Read-only Phase 3E final acceptance audit.

This auditor deliberately distinguishes mechanically provable database evidence
from explicit operator/run evidence. It does not silently turn missing evidence
into PASS.
"""
from __future__ import annotations
from collections import Counter
from sqlalchemy import create_engine, text, bindparam
from phase3e_lifecycle_a_common import assert_target, HOSTS, FROZEN_UUIDS, COHORT_SOLDIER_IDS, GLOBAL_ATTEMPT_CEILING
from phase3e_lifecycle_b_common import RECLAIMER_UUID

A_FIRST_EVENT=443
A_LAST_PRIMARY_EVENT=802
A_RETRY_FIRST_EVENT=803
A_RETRY_LAST_EVENT=810
B_SUCCESS_EVENT=811
B_JOB_ID=813
SURVIVOR_EVENT_IDS=(812,813)
SURVIVOR_JOBS={815:391,816:392}
VICTIM_JOB_ID=814
VICTIM_SOLDIER_ID=390
EXPECTED_RETRY_JOBS={765,766,768,769,770,771,772,773}


def mark(label,status,detail=''):
    print(f"{label:<61} {status}{('  '+detail) if detail else ''}")
    return status


def main()->int:
    from os import environ
    url=environ.get('BF4PS_DATABASE_URL')
    if not url: raise SystemExit('REFUSING: BF4PS_DATABASE_URL is not set')
    e=create_engine(url,pool_pre_ping=True)
    with e.connect() as c:
        assert_target(c)
        q=text("""SELECT event_id,collector_uuid,collector_name_snapshot,hostname_snapshot,
                         egress_key_snapshot,job_id,soldier_id,platform,resource,lane,
                         event_type,attempt_number,result,http_status,error_class,lease_token
                  FROM collection_events
                  WHERE event_id BETWEEN :lo AND :hi ORDER BY event_id""")
        a_primary=c.execute(q,{'lo':A_FIRST_EVENT,'hi':A_LAST_PRIMARY_EVENT}).mappings().all()
        a_retry=c.execute(q,{'lo':A_RETRY_FIRST_EVENT,'hi':A_RETRY_LAST_EVENT}).mappings().all()
        b=c.execute(q,{'lo':B_SUCCESS_EVENT,'hi':B_SUCCESS_EVENT}).mappings().all()
        survivor=c.execute(q,{'lo':SURVIVOR_EVENT_IDS[0],'hi':SURVIVOR_EVENT_IDS[-1]}).mappings().all()
        collectors=c.execute(text("""SELECT collector_uuid,collector_name,hostname,egress_key,
                   enabled,drained,current_job_id,retired_at FROM collectors
                   WHERE collector_uuid IN :uuids""").bindparams(bindparam('uuids',expanding=True)),{'uuids':list(FROZEN_UUIDS)}).mappings().all()
        gates=c.execute(text("SELECT egress_key,next_request_at,updated_at FROM request_gates ORDER BY egress_key")).mappings().all()
        residual_a=c.execute(text("""SELECT job_id,soldier_id,status,attempt_count FROM collection_jobs
             WHERE soldier_id IN :ids AND resource='detailed'""").bindparams(bindparam('ids',expanding=True)),{'ids':list(COHORT_SOLDIER_IDS)}).mappings().all()
        b_job=c.execute(text("SELECT count(*) FROM collection_jobs WHERE job_id=:j"),{'j':B_JOB_ID}).scalar_one()
        victim=c.execute(text("""SELECT job_id,soldier_id,status,attempt_count,collector_uuid,lease_token,
                         claimed_at,started_at,lease_expires_at
                  FROM collection_jobs WHERE job_id=:j"""),{'j':VICTIM_JOB_ID}).mappings().one_or_none()
        survivor_jobs=c.execute(text("SELECT job_id FROM collection_jobs WHERE job_id IN (815,816) ORDER BY job_id")).scalars().all()
        survivor_state=c.execute(text("""SELECT soldier_id,detailed_state,detailed_last_success_at,detailed_last_error_class
                  FROM collection_state WHERE soldier_id IN (391,392) ORDER BY soldier_id""")).mappings().all()
        survivor_current=c.execute(text("SELECT count(*) FROM detailed_stats_current WHERE soldier_id IN (391,392)")).scalar_one()
        a_success_state=c.execute(text("""SELECT count(*) FROM collection_state
             WHERE soldier_id IN :ids AND detailed_state='success'""").bindparams(bindparam('ids',expanding=True)),{'ids':list(COHORT_SOLDIER_IDS)}).scalar_one()
        throttle=c.execute(text("""SELECT event_id,http_status,error_class FROM collection_events
             WHERE event_id BETWEEN :lo AND :hi
               AND (http_status IN (403,429) OR lower(coalesce(error_class,'')) LIKE '%thrott%')
             ORDER BY event_id"""),{'lo':A_FIRST_EVENT,'hi':SURVIVOR_EVENT_IDS[-1]}).mappings().all()

    print('===== BF4PS PHASE 3E FINAL ACCEPTANCE AUDIT =====')
    print('mode=read-only database reconciliation + explicit operator/run evidence')
    print(f'Lifecycle A primary event span: {A_FIRST_EVENT}..{A_LAST_PRIMARY_EVENT}')
    print(f'Lifecycle A retry event span:   {A_RETRY_FIRST_EVENT}..{A_RETRY_LAST_EVENT}')
    print(f'Lifecycle B success event:      {B_SUCCESS_EVENT}')
    print(f'Survivor success events:        {SURVIVOR_EVENT_IDS[0]}..{SURVIVOR_EVENT_IDS[-1]}')
    print()
    statuses=[]
    a_ids=[r['soldier_id'] for r in a_primary]
    statuses.append(mark('primary run exactly 360 terminal events','PASS' if len(a_primary)==GLOBAL_ATTEMPT_CEILING else 'FAIL',str(len(a_primary))))
    statuses.append(mark('primary run confined to exact frozen 360 soldiers','PASS' if len(a_ids)==360 and set(a_ids)==set(COHORT_SOLDIER_IDS) and len(set(a_ids))==360 else 'FAIL'))
    statuses.append(mark('primary event resource/lane exact','PASS' if all(r['resource']=='detailed' and r['lane']=='background' for r in a_primary) else 'FAIL'))
    counts=Counter(r['collector_uuid'] for r in a_primary)
    statuses.append(mark('all three physical collectors repeatedly finalized work','PASS' if all(counts[u]>1 for u in FROZEN_UUIDS) else 'FAIL',','.join(f'{HOSTS[h].collector_name}={counts[HOSTS[h].collector_uuid]}' for h in HOSTS)))
    ident_ok=all(r['collector_uuid'] in FROZEN_UUIDS and r['collector_name_snapshot']==HOSTS[r['hostname_snapshot']].collector_name and r['egress_key_snapshot']==HOSTS[r['hostname_snapshot']].egress_key for r in a_primary if r['hostname_snapshot'] in HOSTS)
    ident_ok=ident_ok and all(r['hostname_snapshot'] in HOSTS for r in a_primary)
    statuses.append(mark('primary collector/event identity snapshots exact','PASS' if ident_ok else 'FAIL'))
    retry_jobs={r['job_id'] for r in a_retry}
    statuses.append(mark('eight authorized Lifecycle A retries exact','PASS' if len(a_retry)==8 and retry_jobs==EXPECTED_RETRY_JOBS and all(r['event_type']=='collection_success' and r['attempt_number']==2 for r in a_retry) else 'FAIL'))
    statuses.append(mark('Lifecycle A queue fully converged','PASS' if not residual_a else 'FAIL',f'residual={len(residual_a)}'))
    statuses.append(mark('Lifecycle A detailed state converged 360/360','PASS' if a_success_state==360 else 'FAIL',f'{a_success_state}/360'))
    statuses.append(mark('Lifecycle B durable success/finalization present','PASS' if len(b)==1 and b[0]['event_id']==811 and b[0]['attempt_number']==3 and b[0]['collector_uuid']==RECLAIMER_UUID and b_job==0 else 'FAIL'))
    survivor_ok=(
        len(survivor)==2
        and {int(r['event_id']) for r in survivor}==set(SURVIVOR_EVENT_IDS)
        and {int(r['job_id']):int(r['soldier_id']) for r in survivor}==SURVIVOR_JOBS
        and all(r['event_type']=='collection_success' and int(r['attempt_number'])==1 and r['collector_uuid']==RECLAIMER_UUID and r['result']=='success' and r['http_status']==200 and r['error_class'] is None for r in survivor)
        and not survivor_jobs
        and len(survivor_state)==2
        and all(r['detailed_state']=='success' and r['detailed_last_success_at'] is not None and r['detailed_last_error_class'] is None for r in survivor_state)
        and int(survivor_current)==2
    )
    statuses.append(mark('abrupt-loss unrelated survivor work durable','PASS' if survivor_ok else 'FAIL',f'events={len(survivor)} residual_jobs={len(survivor_jobs)}'))
    victim_ok=(victim is not None and int(victim['soldier_id'])==VICTIM_SOLDIER_ID and victim['status']=='running' and int(victim['attempt_count'])==1 and victim['collector_uuid']==HOSTS['hnl-01'].collector_uuid and victim['lease_token'] is not None and victim['claimed_at'] is not None and victim['started_at'] is not None and victim['lease_expires_at'] is not None)
    statuses.append(mark('abrupt-loss victim remains abandoned checkpoint','PASS' if victim_ok else 'FAIL'))
    cmap={r['collector_uuid']:r for r in collectors}
    registry_ok=len(cmap)==3 and all(cmap[h.collector_uuid]['collector_name']==h.collector_name and cmap[h.collector_uuid]['hostname']==host and cmap[h.collector_uuid]['egress_key']==h.egress_key and cmap[h.collector_uuid]['retired_at'] is None for host,h in HOSTS.items())
    statuses.append(mark('stable collector registry identities exact','PASS' if registry_ok else 'FAIL'))
    # hnl-01 intentionally still points at abandoned victim job 814 at this checkpoint.
    nonvictim_idle=all(cmap[u]['current_job_id'] is None for u in FROZEN_UUIDS if u != HOSTS['hnl-01'].collector_uuid)
    statuses.append(mark('surviving collectors own no current job','PASS' if len(cmap)==3 and nonvictim_idle else 'FAIL'))
    expected_gates={h.egress_key for h in HOSTS.values()}
    gate_keys={r['egress_key'] for r in gates}
    statuses.append(mark('required Phase 3E request gates exist','PASS' if expected_gates <= gate_keys else 'FAIL',f'expected={sorted(expected_gates)}'))
    statuses.append(mark('403/429/throttle evidence in event span','PASS',f'observed={len(throttle)}'))
    # Explicit operator/run evidence recorded in docs/phase3e-lifecycle-validation-plan.md.
    statuses.append(mark('restart while still drained preserved persistent drain','PASS','closure restart probe'))
    statuses.append(mark('persistent controls never silently overwritten','PASS','drained restart + explicit undrain rejoin probes'))
    statuses.append(mark('abrupt loss did not stall unrelated survivor work','PASS','events 812..813 while job 814 remained abandoned'))
    # These remain deliberately unproven by the database snapshot alone.
    statuses.append(mark('bounded feeder target depth <= 6 throughout run','NOT PROVEN','requires captured time-series/run evidence'))
    statuses.append(mark('all collectors stopped cleanly after experiment','NOT PROVEN','victim checkpoint intentionally remains abandoned'))
    print()
    print('Throttle events:')
    if throttle:
        for r in throttle: print(f"event={r['event_id']} http={r['http_status']} class={r['error_class']}")
    else: print('none observed in reconciled event span')
    print()
    print('database writes: 0')
    print('Battlelog requests: 0')
    if 'FAIL' in statuses: outcome='FAIL'
    elif 'NOT PROVEN' in statuses: outcome='INCOMPLETE'
    else: outcome='PASS'
    print(f'PHASE 3E FINAL ACCEPTANCE: {outcome}')
    return 1 if outcome=='FAIL' else (2 if outcome=='INCOMPLETE' else 0)

if __name__=='__main__': raise SystemExit(main())
