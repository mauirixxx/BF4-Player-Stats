#!/usr/bin/env python3
"""Live Phase 1 retryable-failure and recovery validation against a test DB."""

from __future__ import annotations

import os
import socket
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import create_engine, text

from bf4ps.battlelog_detailed import DetailedStatsTransportError
from bf4ps.collection_jobs import claim_next_job, mark_job_running
from bf4ps.detailed_collector import CollectorIdentity, collect_one_detailed_job
from bf4ps.detailed_failure import classify_detailed_failure, persist_detailed_retry_failure

PERSONA_ID = 236753552
PLATFORM = "pc"
PLAYER = "mauirixxx"
EGRESS_KEY = "phase1-failure-recovery-tcou"


def scalar(conn, sql: str, params=None):
    return conn.execute(text(sql), params or {}).scalar_one()


def main() -> None:
    print("===== BF4PS PHASE 1 FAILURE / RECOVERY =====\n")
    engine = create_engine(os.environ["BF4PS_DATABASE_URL"])

    with engine.connect() as conn:
        db = scalar(conn, "SELECT current_database()")
        recovery = scalar(conn, "SELECT pg_is_in_recovery()")
    print(f"database:       {db}")
    print(f"recovery:       {recovery}")
    if "test" not in db.lower():
        raise SystemExit(f"REFUSING: not a test database: {db}")
    if recovery:
        raise SystemExit("REFUSING: database is in recovery")

    collector_uuid = uuid4()
    collector_name = f"phase1-failure-{collector_uuid.hex[:8]}"
    identity = CollectorIdentity(collector_uuid, collector_name, socket.gethostname(), EGRESS_KEY)

    with engine.begin() as conn:
        soldier = conn.execute(text("""
            SELECT soldier_id, current_name FROM soldiers
            WHERE persona_id=:persona_id AND platform=:platform
        """), {"persona_id": PERSONA_ID, "platform": PLATFORM}).mappings().one()
        soldier_id = int(soldier["soldier_id"])
        current_before = conn.execute(text("SELECT * FROM detailed_stats_current WHERE soldier_id=:s"), {"s": soldier_id}).mappings().one()
        history_before = scalar(conn, "SELECT count(*) FROM detailed_stats_history WHERE soldier_id=:s", {"s": soldier_id})
        state_before = conn.execute(text("SELECT * FROM collection_state WHERE soldier_id=:s"), {"s": soldier_id}).mappings().one()

        conn.execute(text("""
            INSERT INTO collectors
                (collector_uuid, collector_name, hostname, lane, egress_key,
                 enabled, drained, heartbeat_state, started_at, last_heartbeat_at)
            VALUES (:u,:n,:h,'background',:e,true,false,'healthy',now(),now())
        """), {"u": collector_uuid, "n": collector_name, "h": socket.gethostname(), "e": EGRESS_KEY})
        conn.execute(text("""
            INSERT INTO collection_jobs
                (soldier_id, resource, lane, priority_class, reason, status,
                 priority_value, eligible_at)
            VALUES (:s,'detailed','background','interactive','phase1_failure_recovery',
                    'pending',1000,now())
            ON CONFLICT (soldier_id, resource) DO UPDATE
            SET status='pending', eligible_at=now(), collector_uuid=NULL,
                lease_token=NULL, claimed_at=NULL, started_at=NULL,
                lease_expires_at=NULL, updated_at=now()
        """), {"s": soldier_id})

    print(f"soldier:        {soldier['current_name']} ({PERSONA_ID}, {PLATFORM})")
    print(f"soldier_id:     {soldier_id}")
    print(f"collector_uuid: {collector_uuid}")
    print("\nInjecting one controlled retryable transport failure (NO Battlelog request)...")

    with engine.begin() as conn:
        job = claim_next_job(conn, collector_uuid=collector_uuid, lane="background", resource="detailed", lease_seconds=120)
        if job is None or job.soldier_id != soldier_id:
            raise RuntimeError("did not claim expected Patient Zero job")
        if not mark_job_running(conn, job):
            raise RuntimeError("could not transition injected job to running")

    attempted_at = datetime.now(timezone.utc)
    injected = DetailedStatsTransportError("Phase 1 controlled transport failure")
    failure = classify_detailed_failure(injected)
    with engine.begin() as conn:
        persist_detailed_retry_failure(
            conn, job=job, failure=failure, attempted_at=attempted_at,
            persona_id=PERSONA_ID, platform=PLATFORM,
            collector_name=collector_name, hostname=socket.gethostname(),
            egress_key=EGRESS_KEY, duration_ms=0, retry_after_seconds=60,
        )

    with engine.connect() as conn:
        current_after = conn.execute(text("SELECT * FROM detailed_stats_current WHERE soldier_id=:s"), {"s": soldier_id}).mappings().one()
        history_after = scalar(conn, "SELECT count(*) FROM detailed_stats_history WHERE soldier_id=:s", {"s": soldier_id})
        state_failure = conn.execute(text("SELECT * FROM collection_state WHERE soldier_id=:s"), {"s": soldier_id}).mappings().one()
        queued = conn.execute(text("SELECT * FROM collection_jobs WHERE job_id=:j"), {"j": job.job_id}).mappings().one()
        failure_event = conn.execute(text("""
            SELECT * FROM collection_events
            WHERE job_id=:j AND event_type='collection_failure'
            ORDER BY event_id DESC LIMIT 1
        """), {"j": job.job_id}).mappings().one()

    ignored_current = {"updated_at", "source_fetched_at"}
    same_current = all(current_before[k] == current_after[k] for k in current_before if k not in ignored_current)
    assert same_current, "last-known-good current statistics changed during failure"
    assert history_after == history_before, "history changed during failure"
    assert state_failure["detailed_last_success_at"] == state_before["detailed_last_success_at"], "last success changed during failure"
    assert state_failure["detailed_state"] == "temporary_failure"
    assert state_failure["detailed_consecutive_failures"] == state_before["detailed_consecutive_failures"] + 1
    assert state_failure["detailed_last_error_class"] == "battlelog_transport"
    assert queued["status"] == "pending" and queued["collector_uuid"] is None and queued["lease_token"] is None
    assert queued["eligible_at"] > attempted_at
    assert failure_event["result"] == "temporary_failure" and failure_event["error_class"] == "battlelog_transport"

    print("\n===== FAILURE VALIDATION =====")
    print("current stats preserved: PASS")
    print("history preserved:       PASS")
    print("last success preserved:  PASS")
    print("temporary failure state: PASS")
    print("failure count increment: PASS")
    print("structured failure event:PASS")
    print("job pending/recoverable: PASS")
    print("ownership cleared:       PASS")

    print("\nMaking the same job immediately eligible, then performing one real recovery collection...")
    with engine.begin() as conn:
        conn.execute(text("UPDATE collection_jobs SET eligible_at=now() WHERE job_id=:j"), {"j": job.job_id})

    result = collect_one_detailed_job(engine, identity=identity, request_interval_seconds=1.0)
    if result is None or result.job_id != job.job_id:
        raise RuntimeError("recovery collector did not complete expected job")

    with engine.connect() as conn:
        state_recovered = conn.execute(text("SELECT * FROM collection_state WHERE soldier_id=:s"), {"s": soldier_id}).mappings().one()
        remaining = scalar(conn, "SELECT count(*) FROM collection_jobs WHERE job_id=:j", {"j": job.job_id})
        success_event = scalar(conn, "SELECT count(*) FROM collection_events WHERE job_id=:j AND event_type='collection_success'", {"j": job.job_id})

    assert state_recovered["detailed_state"] == "success"
    assert state_recovered["detailed_consecutive_failures"] == 0
    assert state_recovered["detailed_last_error_class"] is None
    assert remaining == 0
    assert success_event >= 1

    print("\n===== RECOVERY VALIDATION =====")
    print("real Battlelog recovery: PASS")
    print("state returned success:  PASS")
    print("failure count reset:     PASS")
    print("last error cleared:      PASS")
    print("queue finalized:         PASS")
    print("success event recorded:  PASS")
    print(f"history appended:        {result.history_appended}")
    print(f"duration_ms:             {result.duration_ms}")

    with engine.begin() as conn:
        gate_cleanup = conn.execute(text("DELETE FROM request_gates WHERE egress_key=:e"), {"e": EGRESS_KEY}).rowcount
        collector_cleanup = conn.execute(text("DELETE FROM collectors WHERE collector_uuid=:u"), {"u": collector_uuid}).rowcount
    print(f"gate cleanup:            {gate_cleanup}")
    print(f"collector cleanup:       {collector_cleanup}")
    print("\nFailure and recovery events/statistics were intentionally retained.")
    print("\nBF4PS PHASE 1 FAILURE / RECOVERY: PASS")


if __name__ == "__main__":
    main()
