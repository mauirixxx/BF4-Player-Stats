#!/usr/bin/env python3
"""Reclaim/finalize abandoned Phase 3E victim job 814 on kah-01."""
from __future__ import annotations
import socket
from sqlalchemy import create_engine, text
from bf4ps.collector_runtime import heartbeat_collector
from bf4ps.detailed_collector import CollectorIdentity, CollectedJob, FailedJob, collect_one_detailed_job
from phase3e_closure_survivor_cohort import VICTIM_SOLDIER_ID
from phase3e_lifecycle_b_common import RECLAIMER_HOST, RECLAIMER_UUID, VICTIM_UUID, assert_target, database_url

JOB_ID = 814

def main() -> int:
    host = socket.gethostname().split(".")[0]
    if host != RECLAIMER_HOST:
        raise SystemExit(f"REFUSING: must run on {RECLAIMER_HOST}, got {host}")
    engine = create_engine(database_url(), pool_pre_ping=True)

    with engine.begin() as conn:
        assert_target(conn)
        control = heartbeat_collector(conn, collector_uuid=RECLAIMER_UUID,
                                      software_version="phase3e-closure-victim-finalize")
        if not control.may_claim:
            raise RuntimeError("reclaimer collector is disabled or drained")
        victim = conn.execute(text("""
            SELECT job_id,soldier_id,resource,lane,status,attempt_count,
                   collector_uuid,lease_token,claimed_at,started_at,lease_expires_at
            FROM collection_jobs WHERE job_id=:j
        """), {"j": JOB_ID}).mappings().one_or_none()
        if victim is None:
            raise RuntimeError("victim job 814 is missing")
        if not (
            int(victim["soldier_id"]) == VICTIM_SOLDIER_ID
            and victim["resource"] == "detailed"
            and victim["lane"] == "background"
            and victim["status"] == "running"
            and int(victim["attempt_count"]) == 1
            and victim["collector_uuid"] == VICTIM_UUID
            and victim["lease_token"] is not None
            and victim["claimed_at"] is not None
            and victim["started_at"] is not None
            and victim["lease_expires_at"] is not None
        ):
            raise RuntimeError(f"unexpected abandoned victim shape: {dict(victim)}")
        expired = conn.execute(text("SELECT :x <= now()"), {"x": victim["lease_expires_at"]}).scalar_one()
        if not expired:
            raise RuntimeError("victim lease has not expired")
        old_events = conn.execute(text("""
            SELECT event_id FROM collection_events WHERE job_id=:j
        """), {"j": JOB_ID}).scalars().all()
        if old_events:
            raise RuntimeError(f"victim already has terminal events: {old_events}")
        identity = conn.execute(text("""
            SELECT collector_name,hostname,egress_key,lane
            FROM collectors WHERE collector_uuid=:u
        """), {"u": RECLAIMER_UUID}).mappings().one()

    ci = CollectorIdentity(
        collector_uuid=RECLAIMER_UUID, collector_name=identity["collector_name"],
        hostname=identity["hostname"], egress_key=identity["egress_key"], lane=identity["lane"]
    )

    print("===== BF4PS PHASE 3E ABANDONED-VICTIM CLOSURE =====", flush=True)
    print(f"host: {host}", flush=True)
    print(f"victim job: {JOB_ID} soldier={VICTIM_SOLDIER_ID} abandoned attempt=1", flush=True)
    print(f"abandoned owner: {victim['collector_uuid']}", flush=True)
    print(f"abandoned token: {victim['lease_token']}", flush=True)
    print("lease expired: PASS", flush=True)
    print("authorized Battlelog requests: at most 1", flush=True)

    result = collect_one_detailed_job(
        engine, identity=ci, request_interval_seconds=5.0, lease_seconds=120,
        timeout_seconds=15.0, retry_after_seconds=300,
        allowed_soldier_ids=(VICTIM_SOLDIER_ID,), max_total_attempts=2,
    )
    if result is None:
        raise RuntimeError("production collector did not reclaim job 814")
    if result.job_id != JOB_ID or result.soldier_id != VICTIM_SOLDIER_ID:
        raise RuntimeError(f"foreign job collected: {result}")
    if isinstance(result, FailedJob):
        raise RuntimeError(f"source failure: class={result.error_class} http={result.http_status}")
    if not isinstance(result, CollectedJob):
        raise RuntimeError(f"unexpected result: {result}")

    with engine.begin() as conn:
        assert_target(conn)
        remaining = conn.execute(text("SELECT count(*) FROM collection_jobs WHERE job_id=:j"),
                                 {"j": JOB_ID}).scalar_one()
        events = conn.execute(text("""
            SELECT event_id,event_type,attempt_number,result,http_status,error_class,
                   collector_uuid,lease_token
            FROM collection_events WHERE job_id=:j ORDER BY event_id
        """), {"j": JOB_ID}).mappings().all()
        state = conn.execute(text("""
            SELECT detailed_state,detailed_last_success_at,detailed_last_error_class
            FROM collection_state WHERE soldier_id=:s
        """), {"s": VICTIM_SOLDIER_ID}).mappings().one()
        current = conn.execute(text("""
            SELECT count(*) FROM detailed_stats_current WHERE soldier_id=:s
        """), {"s": VICTIM_SOLDIER_ID}).scalar_one()
        reclaimer_job = conn.execute(text("""
            SELECT current_job_id FROM collectors WHERE collector_uuid=:u
        """), {"u": RECLAIMER_UUID}).scalar_one()

    if int(remaining) != 0:
        raise RuntimeError("job 814 remains in queue")
    if len(events) != 1:
        raise RuntimeError(f"expected one terminal event, found {len(events)}")
    ev = events[0]
    if not (
        ev["event_type"] == "collection_success"
        and int(ev["attempt_number"]) == 2
        and ev["result"] == "success"
        and ev["http_status"] == 200
        and ev["error_class"] is None
        and ev["collector_uuid"] == RECLAIMER_UUID
        and ev["lease_token"] != victim["lease_token"]
    ):
        raise RuntimeError(f"unexpected terminal event: {dict(ev)}")
    if not (
        state["detailed_state"] == "success"
        and state["detailed_last_success_at"] is not None
        and state["detailed_last_error_class"] is None
        and int(current) == 1
    ):
        raise RuntimeError(f"persistence did not converge: state={dict(state)} current={current}")
    if reclaimer_job is not None:
        raise RuntimeError(f"reclaimer still owns current_job_id={reclaimer_job}")

    print(f"SUCCESS job={result.job_id} soldier={result.soldier_id} history_appended={result.history_appended}")
    print(f"terminal event: {ev['event_id']} attempt={ev['attempt_number']} http={ev['http_status']}")
    print("cross-host reclamation: PASS")
    print("attempt increment 1 -> 2: PASS")
    print("lease-token rotation: PASS")
    print("queue finalization: PASS")
    print("detailed state/current persistence: PASS")
    print("reclaimer cleanly released current job: PASS")
    print("PHASE 3E ABANDONED-VICTIM CLOSURE: PASS")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
