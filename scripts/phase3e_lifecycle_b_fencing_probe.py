#!/usr/bin/env python3
"""Prove Lifecycle B attempt-1 credentials cannot mutate reclaimed job 813.

Uses production queue mutation primitives inside a transaction that is always
rolled back. No Battlelog request is performed.
"""
from __future__ import annotations
from uuid import UUID
from sqlalchemy import create_engine, text
from bf4ps.collection_jobs import ClaimedJob, mark_job_running, renew_lease, release_for_retry, finalize_owned_job
from phase3e_lifecycle_b_common import *
from phase3e_lifecycle_b_cohort import SOLDIER_ID

JOB_ID=813
STALE_TOKEN=UUID("9ad8057a-57fe-4cdb-82fa-49fc58c4ea39")
NEW_TOKEN=UUID("d912e36b-902f-4b5a-bb52-36576c5d6892")


def snapshot(c):
    return c.execute(text("""
        SELECT job_id,soldier_id,status,attempt_count,collector_uuid,lease_token,
               claimed_at,started_at,lease_expires_at,eligible_at,last_error_class,last_error_at
        FROM collection_jobs WHERE job_id=:j
    """),{'j':JOB_ID}).mappings().one_or_none()


def main()->int:
    e=create_engine(database_url(),pool_pre_ping=True)
    conn=e.connect(); tx=conn.begin()
    try:
        assert_target(conn)
        before=snapshot(conn)
        if before is None: raise RuntimeError("Lifecycle B job 813 is missing")
        expected=(int(before['soldier_id'])==SOLDIER_ID and before['status']=='running'
                  and int(before['attempt_count'])==2 and before['collector_uuid']==RECLAIMER_UUID
                  and before['lease_token']==NEW_TOKEN)
        if not expected: raise RuntimeError(f"unexpected attempt-2 ownership state: {dict(before)}")
        stale=ClaimedJob(job_id=JOB_ID,soldier_id=SOLDIER_ID,resource=RESOURCE,lane=LANE,
                         attempt_count=1,collector_uuid=VICTIM_UUID,lease_token=STALE_TOKEN)
        results={
            'mark_job_running': mark_job_running(conn,stale),
            'renew_lease': renew_lease(conn,stale,lease_seconds=LEASE_SECONDS),
            'release_for_retry': release_for_retry(conn,stale,retry_after_seconds=0),
            'finalize_owned_job': finalize_owned_job(conn,stale),
        }
        after=snapshot(conn)
        if any(results.values()): raise RuntimeError(f"STALE OWNER MUTATION ACCEPTED: {results}")
        if dict(after)!=dict(before): raise RuntimeError(f"job changed during stale-owner probe: before={dict(before)} after={dict(after)}")
        tx.rollback()
        tx=None
        with e.connect() as verify:
            persisted=snapshot(verify)
        if dict(persisted)!=dict(before): raise RuntimeError("persisted job changed across rollback/verification")
    finally:
        if tx is not None and tx.is_active: tx.rollback()
        conn.close()
    print("===== BF4PS PHASE 3E LIFECYCLE B STALE-OWNER FENCING =====")
    print(f"job:              {JOB_ID}")
    print(f"current attempt:  {before['attempt_count']}")
    print(f"current owner:    {before['collector_uuid']}")
    print(f"current token:    {before['lease_token']}")
    print(f"stale owner:      {VICTIM_UUID}")
    print(f"stale token:      {STALE_TOKEN}")
    for name,value in results.items(): print(f"{name:<22} {'REJECTED' if not value else 'ACCEPTED'}")
    print("row unchanged in transaction: PASS")
    print("row unchanged after rollback: PASS")
    print("database writes persisted: 0")
    print("Battlelog requests: 0")
    print("LIFECYCLE B STALE-OWNER FENCING: PASS")
    return 0

if __name__=='__main__': raise SystemExit(main())
