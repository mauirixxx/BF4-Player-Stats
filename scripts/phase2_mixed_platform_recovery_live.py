#!/usr/bin/env python3
"""One-attempt live recovery proof for the retained Phase 2 mixed-platform incident."""
from __future__ import annotations
import os
from uuid import UUID
from sqlalchemy import create_engine, text
from bf4ps.detailed_collector import CollectorIdentity
from bf4ps.single_node_runtime import SingleNodeRuntimeConfig, run_bounded_single_node

EXPECTED_REVISION = "0003_request_gates"
EXPECTED_IDS = (17, 18, 19, 93, 94, 95, 105, 106, 107)
EXPECTED_SUCCESSES = (17, 18, 19, 93, 94, 95, 105, 106)
TARGET = 107
COLLECTOR_UUID = UUID("b2b3ef60-62e8-4d4a-91b0-41a2e2a20004")
IDENTITY = CollectorIdentity(
    collector_uuid=COLLECTOR_UUID,
    collector_name="phase2-mixed-recovery-tcou",
    hostname="tcou",
    egress_key="phase2-mixed-tcou",
    lane="background",
)

def cohort_rows(conn):
    return conn.execute(text("""
        SELECT s.soldier_id, s.platform, s.current_name,
               cs.detailed_state, cs.detailed_last_attempt_at,
               cs.detailed_last_success_at, cs.detailed_next_due_at,
               cs.detailed_consecutive_failures, dsc.source_fetched_at
        FROM soldiers AS s
        JOIN collection_state AS cs ON cs.soldier_id = s.soldier_id
        LEFT JOIN detailed_stats_current AS dsc ON dsc.soldier_id = s.soldier_id
        WHERE s.soldier_id = ANY(:ids)
        ORDER BY s.soldier_id
    """), {"ids": list(EXPECTED_IDS)}).mappings().all()

def main():
    engine = create_engine(os.environ["BF4PS_DATABASE_URL"])
    with engine.connect() as conn:
        db = conn.execute(text("SELECT current_database()")).scalar_one()
        recovery = conn.execute(text("SELECT pg_is_in_recovery()")).scalar_one()
        revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        queue_count = conn.execute(text("""
            SELECT COUNT(*) FROM collection_jobs
            WHERE resource = 'detailed' AND lane = 'background'
        """)).scalar_one()
        before = cohort_rows(conn)

    if "test" not in db.lower():
        raise SystemExit(f"REFUSING: not a test database: {db}")
    if recovery:
        raise SystemExit("REFUSING: database is in recovery")
    if revision != EXPECTED_REVISION:
        raise SystemExit(f"REFUSING: expected {EXPECTED_REVISION}, found {revision}")
    if queue_count != 0:
        raise SystemExit(f"REFUSING: detailed/background queue has {queue_count} row(s)")
    if tuple(r["soldier_id"] for r in before) != EXPECTED_IDS:
        raise SystemExit("REFUSING: frozen cohort identities changed")

    successes = tuple(r["soldier_id"] for r in before if r["detailed_state"] == "success")
    never = tuple(r["soldier_id"] for r in before if r["detailed_state"] == "never_attempted")
    other = tuple((r["soldier_id"], r["detailed_state"]) for r in before
                  if r["detailed_state"] not in {"success", "never_attempted"})
    target_before = next(r for r in before if r["soldier_id"] == TARGET)

    if successes != EXPECTED_SUCCESSES or never != (TARGET,) or other:
        raise SystemExit(f"REFUSING: retained state changed: success={successes}, never={never}, other={other}")
    if target_before["source_fetched_at"] is not None:
        raise SystemExit("REFUSING: soldier 107 already has detailed current data")

    print("===== BF4PS PHASE 2 MIXED-PLATFORM RECOVERY LIVE RUN =====\n")
    print(f"database:       {db}")
    print(f"recovery:       {recovery}")
    print(f"alembic:        {revision}")
    print(f"collector_uuid: {COLLECTOR_UUID}")
    print(f"retained success: {list(successes)}")
    print(f"remaining:      {list(never)}")
    print("target_depth:   1")
    print("max_jobs:       1")
    print("queue empty:    PASS")
    print("retained state: PASS")
    print("\nStarting exactly one bounded recovery attempt...\n")

    result = run_bounded_single_node(
        engine,
        identity=IDENTITY,
        config=SingleNodeRuntimeConfig(
            target_depth=1,
            max_soldier_id=107,
            max_jobs=1,
            request_interval_seconds=2.0,
            feeder_interval_seconds=0.01,
            heartbeat_interval_seconds=15.0,
            idle_sleep_seconds=0.05,
            lease_seconds=120,
            timeout_seconds=15.0,
            retry_after_seconds=300,
            software_version="phase2-mixed-recovery-validation",
            allowed_soldier_ids=EXPECTED_IDS,
        ),
    )

    with engine.connect() as conn:
        after = cohort_rows(conn)
        jobs = conn.execute(text("""
            SELECT job_id, soldier_id, status, eligible_at, attempt_count,
                   last_error_class, last_error_at
            FROM collection_jobs
            WHERE resource = 'detailed' AND lane = 'background'
              AND soldier_id = ANY(:ids)
            ORDER BY job_id
        """), {"ids": list(EXPECTED_IDS)}).mappings().all()
        outside = conn.execute(text("""
            SELECT COUNT(*) FROM collection_jobs
            WHERE resource = 'detailed' AND lane = 'background'
              AND NOT (soldier_id = ANY(:ids))
        """), {"ids": list(EXPECTED_IDS)}).scalar_one()
        collector = conn.execute(text("""
            SELECT heartbeat_state, enabled, drained, current_job_id
            FROM collectors WHERE collector_uuid = :uuid
        """), {"uuid": COLLECTOR_UUID}).mappings().one()

    print("===== RUNTIME RESULT =====")
    print(f"jobs attempted:    {result.jobs_attempted}")
    print(f"jobs succeeded:    {result.jobs_succeeded}")
    print(f"jobs failed:       {result.jobs_failed}")
    print(f"feeder passes:     {result.feeder_passes}")
    print(f"jobs materialized: {result.jobs_materialized}")
    print(f"stopped by control:{result.stopped_by_control}")

    print("\n===== FINAL COHORT STATE =====")
    for r in after:
        print(f"soldier={r['soldier_id']:<7} {r['platform']:<8} {r['current_name']!r:<24} state={r['detailed_state']}")
        print(f"         last_attempt={r['detailed_last_attempt_at']} last_success={r['detailed_last_success_at']}")
        print(f"         next_due={r['detailed_next_due_at']} failures={r['detailed_consecutive_failures']} source_fetched={r['source_fetched_at']}")

    if result.jobs_attempted != 1 or result.jobs_materialized != 1 or result.feeder_passes != 1:
        raise RuntimeError("expected exactly one attempt, one materialized job, and one feeder pass")
    if result.jobs_succeeded + result.jobs_failed != 1:
        raise RuntimeError("success/failure total does not equal one attempt")
    if result.stopped_by_control or outside != 0:
        raise RuntimeError("runtime boundary/control validation failed")
    if collector["heartbeat_state"] != "unknown" or collector["current_job_id"] is not None:
        raise RuntimeError("collector did not stop cleanly")
    if not collector["enabled"] or collector["drained"]:
        raise RuntimeError("runtime changed operator controls")
    if any(r["detailed_state"] != "success" for r in after if r["soldier_id"] in EXPECTED_SUCCESSES):
        raise RuntimeError("one of the prior eight successes regressed")

    target = next(r for r in after if r["soldier_id"] == TARGET)
    print("\n===== SCHEDULER FIX VALIDATION =====")
    print("exact one feeder pass:             PASS")
    print("exact one job materialized:        PASS")
    print("exact one collection attempt:      PASS")
    print("frozen cohort boundary:            PASS")
    print("prior 8 successes preserved:       PASS")
    print("collector clean stop:              PASS")

    if result.jobs_succeeded == 1:
        if target["detailed_state"] != "success" or target["source_fetched_at"] is None or jobs:
            raise RuntimeError("successful recovery persistence/finalization validation failed")
        print("soldier 107 collected:             PASS")
        print("all 9 soldiers successful:         PASS")
        print("cohort queue finalized:            PASS")
        print("\nNo cleanup performed; recovery evidence is intentionally retained.")
        print("BF4PS PHASE 2 MIXED-PLATFORM RECOVERY LIVE RUN: PASS")
    else:
        if target["detailed_state"] not in {"temporary_failure", "unavailable"}:
            raise RuntimeError("failed source attempt did not persist an attempted state")
        if len(jobs) > 1 or (jobs and jobs[0]["soldier_id"] != TARGET):
            raise RuntimeError("unexpected recoverable queue shape")
        print(f"soldier 107 source result:         {target['detailed_state']}")
        print(f"recoverable cohort queue rows:     {len(jobs)}")
        print("scheduler starvation fixed:        PASS")
        print("\nSource collection failed, but scheduling proof is valid.")
        print("BF4PS PHASE 2 MIXED-PLATFORM RECOVERY SCHEDULING PROOF: PASS")

if __name__ == "__main__":
    main()
