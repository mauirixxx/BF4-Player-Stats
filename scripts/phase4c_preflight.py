#!/usr/bin/env python3
"""Read-only safety preflight for the Phase 4C 450-player multiplatform run."""
from __future__ import annotations
import os, sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit
from sqlalchemy import create_engine, text
sys.path.insert(0, str(Path(__file__).resolve().parent))
from phase4c_cohort import PHASE4C_COHORT, SOLDIER_IDS
from phase4c_common import EXPECTED_DATABASE, EXPECTED_DB_HOST, EXPECTED_PLATFORM_COUNTS, FROZEN_UUIDS, HOSTS, assert_target


def main() -> int:
    url=os.environ.get("BF4PS_DATABASE_URL"); parsed=urlsplit(url or "")
    if not url or parsed.hostname!=EXPECTED_DB_HOST or parsed.path.lstrip("/")!=EXPECTED_DATABASE:
        raise SystemExit("REFUSING: wrong or missing BF4PS_DATABASE_URL")
    engine=create_engine(url,pool_pre_ping=True); ids=list(SOLDIER_IDS); expected={r[0]:r for r in PHASE4C_COHORT}
    with engine.connect() as conn:
        assert_target(conn)
        soldiers=conn.execute(text("SELECT soldier_id,persona_id,current_name,platform FROM soldiers WHERE soldier_id=ANY(:ids) ORDER BY soldier_id"),{"ids":ids}).mappings().all()
        identity_exact=len(soldiers)==450 and all((int(r['soldier_id']),int(r['persona_id']),str(r['current_name']),str(r['platform']))==expected[int(r['soldier_id'])] for r in soldiers)
        platform_dist=Counter(str(r['platform']) for r in soldiers)
        states=conn.execute(text("""SELECT soldier_id,detailed_state,detailed_last_attempt_at,detailed_last_success_at,detailed_next_due_at,detailed_consecutive_failures,detailed_last_error_class,detailed_last_error_message FROM collection_state WHERE soldier_id=ANY(:ids)"""),{"ids":ids}).mappings().all()
        state_dist=Counter(str(r['detailed_state']) for r in states)
        pristine=len(states)==450 and all(r['detailed_state']=='never_attempted' and r['detailed_last_attempt_at'] is None and r['detailed_last_success_at'] is None and r['detailed_next_due_at'] is None and int(r['detailed_consecutive_failures'])==0 and r['detailed_last_error_class'] is None and r['detailed_last_error_message'] is None for r in states)
        cohort_jobs=int(conn.execute(text("SELECT count(*) FROM collection_jobs WHERE resource='detailed' AND soldier_id=ANY(:ids)"),{"ids":ids}).scalar_one())
        foreign_jobs=int(conn.execute(text("SELECT count(*) FROM collection_jobs WHERE resource='detailed' AND lane='background' AND soldier_id<>ALL(:ids)"),{"ids":ids}).scalar_one())
        collectors=conn.execute(text("SELECT collector_uuid,collector_name,hostname,egress_key,enabled,drained,heartbeat_state,current_job_id,retired_at FROM collectors WHERE collector_uuid=ANY(:uuids) ORDER BY hostname"),{"uuids":list(FROZEN_UUIDS)}).mappings().all()
        collector_exact=len(collectors)==3 and all(r['retired_at'] is None and r['hostname'] in HOSTS and r['collector_uuid']==HOSTS[r['hostname']].collector_uuid and r['collector_name']==HOSTS[r['hostname']].collector_name and r['egress_key']==HOSTS[r['hostname']].egress_key and bool(r['enabled']) and not bool(r['drained']) and r['current_job_id'] is None for r in collectors)
        any_owned=int(conn.execute(text("SELECT count(*) FROM collectors WHERE retired_at IS NULL AND current_job_id IS NOT NULL")).scalar_one())
        gates=conn.execute(text("SELECT egress_key,next_request_at,updated_at FROM request_gates WHERE egress_key=ANY(:keys) ORDER BY egress_key"),{"keys":[h.egress_key for h in HOSTS.values()]}).mappings().all()
        gate_exact={r['egress_key'] for r in gates}=={h.egress_key for h in HOSTS.values()}
        prior_terminal=int(conn.execute(text("SELECT count(*) FROM collection_events WHERE resource='detailed' AND lane='background' AND soldier_id=ANY(:ids) AND event_type IN ('collection_success','collection_failure')"),{"ids":ids}).scalar_one())
        throttle=conn.execute(text("SELECT http_status,count(*) n FROM collection_events WHERE http_status IN (403,429) GROUP BY http_status ORDER BY http_status")).all()
    print("===== BF4PS PHASE 4C MULTIPLATFORM SUSTAINED-RUN PREFLIGHT =====")
    print(f"frozen cohort: {len(ids)} soldiers")
    print(f"platform distribution: {dict(platform_dist)}")
    print(f"state distribution: {dict(state_dist)}")
    print("collectors:")
    for r in collectors: print(f"  {r['hostname']:<7} {r['collector_name']:<18} egress={r['egress_key']!r} enabled={r['enabled']} drained={r['drained']} heartbeat={r['heartbeat_state']} current_job={r['current_job_id']}")
    print("request gates:")
    for r in gates: print(f"  {r['egress_key']:<18} next={r['next_request_at']} updated={r['updated_at']}")
    print("historical 403/429:","none" if not throttle else dict(throttle))
    checks=[("exact frozen identities unchanged",identity_exact),("exact 150/150/150 platform distribution",dict(platform_dist)==EXPECTED_PLATFORM_COUNTS),("all 450 detailed states pristine",pristine),("no frozen-cohort detailed jobs exist",cohort_jobs==0),("no foreign detailed/background jobs exist",foreign_jobs==0),("three stable collectors exact/enabled/undrained/idle",collector_exact),("no active collector owns any job",any_owned==0),("three required request gates exist",gate_exact),("no prior Phase 4C terminal events",prior_terminal==0)]
    print("validation:")
    for label,ok in checks: print(f"{label:<62} {'PASS' if ok else 'FAIL'}")
    print("database writes: 0\nBattlelog requests: 0")
    passed=all(ok for _,ok in checks); print(f"PHASE 4C MULTIPLATFORM SUSTAINED-RUN PREFLIGHT: {'PASS' if passed else 'FAIL'}"); return 0 if passed else 1

if __name__=='__main__': raise SystemExit(main())
