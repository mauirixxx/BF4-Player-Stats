#!/usr/bin/env python3
"""Read-only final reconciliation for Phase 3E Lifecycle B."""
from __future__ import annotations
from uuid import UUID
from sqlalchemy import create_engine, text
from phase3e_lifecycle_b_common import *
from phase3e_lifecycle_b_cohort import SOLDIER_ID, PERSONA_ID, PLATFORM

JOB_ID=813
STALE_TOKEN=UUID("9ad8057a-57fe-4cdb-82fa-49fc58c4ea39")
ATTEMPT2_TOKEN=UUID("d912e36b-902f-4b5a-bb52-36576c5d6892")
ATTEMPT3_TOKEN=UUID("5a02a116-ecd9-4ab2-b5c5-4518ef84bc1b")
SUCCESS_EVENT_ID=811


def verdict(label: str, ok: bool) -> bool:
    print(f"{label:<55} {'PASS' if ok else 'FAIL'}")
    return ok


def main() -> int:
    e=create_engine(database_url(),pool_pre_ping=True)
    with e.connect() as c:
        assert_target(c)
        job_count=c.execute(text("SELECT count(*) FROM collection_jobs WHERE job_id=:j"),{'j':JOB_ID}).scalar_one()
        events=c.execute(text("""
            SELECT event_id,occurred_at,collector_uuid,collector_name_snapshot,
                   hostname_snapshot,egress_key_snapshot,job_id,soldier_id,
                   persona_id,platform,resource,lane,event_type,attempt_number,
                   result,http_status,error_class,lease_token,metadata
            FROM collection_events WHERE job_id=:j ORDER BY event_id
        """),{'j':JOB_ID}).mappings().all()
        success=c.execute(text("""
            SELECT event_id,collector_uuid,collector_name_snapshot,hostname_snapshot,
                   egress_key_snapshot,soldier_id,persona_id,platform,resource,lane,
                   event_type,attempt_number,result,http_status,error_class,lease_token
            FROM collection_events WHERE job_id=:j AND event_type='collection_success'
            ORDER BY event_id
        """),{'j':JOB_ID}).mappings().all()
        state=c.execute(text("""
            SELECT detailed_state,detailed_last_attempt_at,detailed_last_success_at,
                   detailed_next_due_at,detailed_consecutive_failures,
                   detailed_last_error_class,detailed_last_error_message
            FROM collection_state WHERE soldier_id=:s
        """),{'s':SOLDIER_ID}).mappings().one_or_none()
        current=c.execute(text("SELECT source_fetched_at FROM detailed_stats_current WHERE soldier_id=:s"),{'s':SOLDIER_ID}).mappings().one_or_none()
        history_count=c.execute(text("SELECT count(*) FROM detailed_stats_history WHERE soldier_id=:s"),{'s':SOLDIER_ID}).scalar_one()
        collectors=c.execute(text("""
            SELECT collector_uuid,collector_name,hostname,egress_key,current_job_id
            FROM collectors WHERE collector_uuid IN (:v,:r) ORDER BY collector_uuid
        """),{'v':VICTIM_UUID,'r':RECLAIMER_UUID}).mappings().all()
        foreign_success=c.execute(text("""
            SELECT count(*) FROM collection_events
            WHERE job_id=:j AND event_type='collection_success'
              AND (collector_uuid<>:r OR attempt_number<>3 OR lease_token<>:t)
        """),{'j':JOB_ID,'r':RECLAIMER_UUID,'t':ATTEMPT3_TOKEN}).scalar_one()

    print("===== BF4PS PHASE 3E LIFECYCLE B FINAL RECONCILIATION =====")
    print(f"job={JOB_ID} soldier={SOLDIER_ID} persona={PERSONA_ID} platform={PLATFORM}")
    print(f"ledger events for job: {len(events)}")
    for ev in events:
        print(f"event={ev['event_id']} type={ev['event_type']} attempt={ev['attempt_number']} collector={ev['collector_name_snapshot']} token={ev['lease_token']} result={ev['result']}")
    print()
    checks=[]
    checks.append(verdict("Lifecycle B queue job fully finalized",job_count==0))
    checks.append(verdict("exactly one successful collection event",len(success)==1))
    s=success[0] if len(success)==1 else None
    checks.append(verdict("success is durable event 811",bool(s and s['event_id']==SUCCESS_EVENT_ID)))
    checks.append(verdict("success occurred only on attempt three",bool(s and s['attempt_number']==3 and foreign_success==0)))
    checks.append(verdict("success owned by kah-01 stable collector",bool(s and s['collector_uuid']==RECLAIMER_UUID and s['collector_name_snapshot']==RECLAIMER_NAME and s['hostname_snapshot']==RECLAIMER_HOST and s['egress_key_snapshot']==RECLAIMER_NAME)))
    checks.append(verdict("success used rotated attempt-three lease token",bool(s and s['lease_token']==ATTEMPT3_TOKEN and s['lease_token'] not in (STALE_TOKEN,ATTEMPT2_TOKEN))))
    checks.append(verdict("success identity/resource/lane exact",bool(s and s['soldier_id']==SOLDIER_ID and s['persona_id']==PERSONA_ID and s['platform']==PLATFORM and s['resource']==RESOURCE and s['lane']==LANE)))
    checks.append(verdict("success HTTP/result clean",bool(s and s['result']=='success' and s['http_status']==200 and s['error_class'] is None)))
    checks.append(verdict("detailed collection state converged to success",bool(state and state['detailed_state']=='success' and state['detailed_last_success_at'] is not None and state['detailed_consecutive_failures']==0 and state['detailed_last_error_class'] is None and state['detailed_last_error_message'] is None)))
    checks.append(verdict("detailed current row persisted",current is not None))
    checks.append(verdict("detailed history snapshot persisted",history_count>=1))
    cmap={r['collector_uuid']:r for r in collectors}
    checks.append(verdict("victim and reclaimer stable identities exact",VICTIM_UUID in cmap and RECLAIMER_UUID in cmap and cmap[VICTIM_UUID]['collector_name']==VICTIM_NAME and cmap[VICTIM_UUID]['hostname']==VICTIM_HOST and cmap[RECLAIMER_UUID]['collector_name']==RECLAIMER_NAME and cmap[RECLAIMER_UUID]['hostname']==RECLAIMER_HOST))
    checks.append(verdict("neither lifecycle collector owns current job",VICTIM_UUID in cmap and RECLAIMER_UUID in cmap and cmap[VICTIM_UUID]['current_job_id'] is None and cmap[RECLAIMER_UUID]['current_job_id'] is None))
    print()
    print("Observed ownership history (operator/harness evidence):")
    print(f"attempt 1: hnl-01 token={STALE_TOKEN} -> owner killed; lease expired")
    print(f"attempt 2: kah-01 token={ATTEMPT2_TOKEN} -> reclaim/fencing checkpoint; lease expired")
    print(f"attempt 3: kah-01 token={ATTEMPT3_TOKEN} -> event {SUCCESS_EVENT_ID} success/finalize")
    print("stale-owner mutation rejection was proven separately by the fencing probe")
    print("database writes: 0")
    print("Battlelog requests: 0")
    ok=all(checks)
    print(f"LIFECYCLE B FINAL RECONCILIATION: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1

if __name__=='__main__': raise SystemExit(main())
