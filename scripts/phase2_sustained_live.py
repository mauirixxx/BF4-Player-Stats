#!/usr/bin/env python3
"""Run the bounded Phase 2 sustained-runtime live validation."""

from __future__ import annotations

import os
from uuid import UUID

from sqlalchemy import create_engine, text

from bf4ps.detailed_collector import CollectorIdentity
from bf4ps.single_node_runtime import SingleNodeRuntimeConfig, run_bounded_single_node

COLLECTOR_UUID = UUID("b2b3ef60-62e8-4d4a-91b0-41a2e2a20002")
IDENTITY = CollectorIdentity(
    collector_uuid=COLLECTOR_UUID,
    collector_name="phase2-sustained-tcou",
    hostname="tcou",
    egress_key="phase2-sustained-tcou",
    lane="background",
)
TARGET_DEPTH = 1
MAX_JOBS = 10
MAX_SOLDIER_ID = 16
EXPECTED_SOLDIER_IDS = set(range(7, 17))


def main() -> None:
    engine = create_engine(os.environ["BF4PS_DATABASE_URL"])

    with engine.connect() as conn:
        db = conn.execute(text("SELECT current_database()")).scalar_one()
        recovery = conn.execute(text("SELECT pg_is_in_recovery()")).scalar_one()
        revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        queue_count = conn.execute(text("""
            SELECT COUNT(*) FROM collection_jobs
            WHERE resource = 'detailed' AND lane = 'background'
        """)).scalar_one()
        candidates = conn.execute(text("""
            SELECT s.soldier_id
            FROM soldiers AS s
            JOIN collection_state AS cs ON cs.soldier_id = s.soldier_id
            WHERE s.soldier_id <= :max_soldier_id
              AND s.platform IN ('pc', 'ps4', 'xboxone')
              AND cs.detailed_state = 'never_attempted'
              AND NOT EXISTS (
                  SELECT 1 FROM collection_jobs AS j
                  WHERE j.soldier_id = s.soldier_id
                    AND j.resource = 'detailed'
              )
            ORDER BY s.soldier_id
        """), {"max_soldier_id": MAX_SOLDIER_ID}).scalars().all()

    if "test" not in db.lower():
        raise SystemExit(f"REFUSING: not a test database: {db}")
    if recovery:
        raise SystemExit("REFUSING: database is in recovery")
    if revision != "0003_request_gates":
        raise SystemExit(f"REFUSING: unexpected Alembic revision: {revision}")
    if queue_count != 0:
        raise SystemExit("REFUSING: detailed/background queue is not empty")
    if set(candidates) != EXPECTED_SOLDIER_IDS:
        raise SystemExit(
            f"REFUSING: cohort changed; expected {sorted(EXPECTED_SOLDIER_IDS)}, "
            f"found {sorted(candidates)}"
        )

    print("===== BF4PS PHASE 2 SUSTAINED LIVE RUN =====\n")
    print(f"database:       {db}")
    print(f"recovery:       {recovery}")
    print(f"alembic:        {revision}")
    print(f"collector_uuid: {COLLECTOR_UUID}")
    print(f"cohort:         {sorted(candidates)}")
    print(f"target_depth:   {TARGET_DEPTH}")
    print(f"max_jobs:       {MAX_JOBS}")
    print(f"max_soldier_id: {MAX_SOLDIER_ID}")
    print("queue empty:    PASS")
    print("cohort exact:   PASS")
    print("\nStarting sustained bounded runtime...\n")

    result = run_bounded_single_node(
        engine,
        identity=IDENTITY,
        config=SingleNodeRuntimeConfig(
            target_depth=TARGET_DEPTH,
            max_soldier_id=MAX_SOLDIER_ID,
            max_jobs=MAX_JOBS,
            request_interval_seconds=2.0,
            feeder_interval_seconds=0.01,
            heartbeat_interval_seconds=15.0,
            idle_sleep_seconds=0.05,
            lease_seconds=120,
            timeout_seconds=15.0,
            retry_after_seconds=300,
            software_version="phase2-sustained-validation",
        ),
    )

    with engine.connect() as conn:
        cohort = conn.execute(text("""
            SELECT s.soldier_id, s.current_name, s.platform,
                   cs.detailed_state, cs.detailed_last_success_at,
                   dsc.source_fetched_at
            FROM soldiers AS s
            JOIN collection_state AS cs ON cs.soldier_id = s.soldier_id
            LEFT JOIN detailed_stats_current AS dsc ON dsc.soldier_id = s.soldier_id
            WHERE s.soldier_id = ANY(:ids)
            ORDER BY s.soldier_id
        """), {"ids": sorted(EXPECTED_SOLDIER_IDS)}).mappings().all()
        remaining_jobs = conn.execute(text("""
            SELECT COUNT(*) FROM collection_jobs
            WHERE resource = 'detailed'
              AND lane = 'background'
              AND soldier_id = ANY(:ids)
        """), {"ids": sorted(EXPECTED_SOLDIER_IDS)}).scalar_one()
        collector = conn.execute(text("""
            SELECT heartbeat_state, enabled, drained, current_job_id
            FROM collectors WHERE collector_uuid = :uuid
        """), {"uuid": COLLECTOR_UUID}).mappings().one()
        beyond_boundary = conn.execute(text("""
            SELECT COUNT(*) FROM collection_jobs
            WHERE resource = 'detailed'
              AND lane = 'background'
              AND soldier_id > :max_soldier_id
        """), {"max_soldier_id": MAX_SOLDIER_ID}).scalar_one()

    print("===== RUNTIME RESULT =====")
    print(f"jobs attempted:    {result.jobs_attempted}")
    print(f"jobs succeeded:    {result.jobs_succeeded}")
    print(f"jobs failed:       {result.jobs_failed}")
    print(f"feeder passes:     {result.feeder_passes}")
    print(f"jobs materialized: {result.jobs_materialized}")
    print(f"stopped by control:{result.stopped_by_control}")

    print("\n===== COHORT STATE =====")
    for row in cohort:
        print(
            f"soldier={row['soldier_id']:<6} {row['platform']:<8} "
            f"{row['current_name']!r:<22} state={row['detailed_state']}"
        )
        print(
            f"         last_success={row['detailed_last_success_at']} "
            f"source_fetched={row['source_fetched_at']}"
        )

    if result.jobs_attempted != MAX_JOBS:
        raise RuntimeError(f"expected {MAX_JOBS} attempts, got {result.jobs_attempted}")
    if result.jobs_succeeded + result.jobs_failed != MAX_JOBS:
        raise RuntimeError("success/failure totals do not equal attempt ceiling")
    if result.jobs_materialized != MAX_JOBS:
        raise RuntimeError(f"expected {MAX_JOBS} materialized jobs, got {result.jobs_materialized}")
    if result.feeder_passes < MAX_JOBS:
        raise RuntimeError("runtime did not repeatedly replenish the depth-one queue")
    if result.stopped_by_control:
        raise RuntimeError("runtime unexpectedly stopped by operator control")
    if collector["heartbeat_state"] != "unknown":
        raise RuntimeError("collector did not stop cleanly")
    if not collector["enabled"] or collector["drained"]:
        raise RuntimeError("runtime changed operator controls")
    if collector["current_job_id"] is not None:
        raise RuntimeError("collector retained current_job_id after stop")
    if beyond_boundary != 0:
        raise RuntimeError("runtime materialized work beyond soldier_id 16")

    attempted_states = {"success", "temporary_failure", "unavailable"}
    if any(row["detailed_state"] not in attempted_states for row in cohort):
        raise RuntimeError("not every sustained-cohort soldier reached an attempted state")

    print("\n===== FINAL VALIDATION =====")
    print("exact 10-attempt ceiling:       PASS")
    print("repeated feeder replenishment:  PASS")
    print("exact 10 jobs materialized:     PASS")
    print("soldier boundary <= 16:         PASS")
    print("collector clean stop:           PASS")
    print("operator controls preserved:    PASS")
    print("all cohort soldiers attempted:  PASS")

    if result.jobs_failed == 0:
        if remaining_jobs != 0:
            raise RuntimeError("all-success cohort left queue rows behind")
        if any(row["detailed_state"] != "success" for row in cohort):
            raise RuntimeError("all-success result disagrees with collection_state")
        if any(row["source_fetched_at"] is None for row in cohort):
            raise RuntimeError("successful cohort is missing detailed current data")
        print("all collections successful:     PASS")
        print("cohort queue finalized:          PASS")
    else:
        print(f"persisted source failures:       {result.jobs_failed}")
        print(f"recoverable queue rows:          {remaining_jobs}")

    print("\nNo cleanup performed; sustained-run evidence is intentionally retained.")
    print("BF4PS PHASE 2 SUSTAINED LIVE RUN: PASS")


if __name__ == "__main__":
    main()
