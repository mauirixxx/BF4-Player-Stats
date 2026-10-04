#!/usr/bin/env python3
"""Run the bounded Phase 3A two-collector live concurrency proof."""

from __future__ import annotations

import os
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from threading import Lock
from uuid import UUID

from sqlalchemy import create_engine, text

from bf4ps.bounded_feeder import replenish_detailed_bootstrap
from bf4ps.collector_runtime import heartbeat_collector, register_collector, stop_collector
from bf4ps.detailed_collector import (
    CollectedJob,
    CollectorIdentity,
    FailedJob,
    collect_one_detailed_job,
)

EXPECTED_REVISION = "0003_request_gates"
COHORT_IDS = (20, 21, 22, 23, 96, 97, 98, 99, 108, 109, 110, 111)
EXPECTED_PLATFORM_COUNTS = {"pc": 4, "ps4": 4, "xboxone": 4}
TARGET_DEPTH = 2
MAX_ATTEMPTS = 12
REQUEST_INTERVAL_SECONDS = 2.0
EGRESS_KEY = "phase3a-concurrent-tcou"
HOSTNAME = socket.gethostname()
IDENTITIES = (
    CollectorIdentity(
        collector_uuid=UUID("b2b3ef60-62e8-4d4a-91b0-41a2e2a30001"),
        collector_name="phase3a-tcou-a",
        hostname=HOSTNAME,
        egress_key=EGRESS_KEY,
        lane="background",
    ),
    CollectorIdentity(
        collector_uuid=UUID("b2b3ef60-62e8-4d4a-91b0-41a2e2a30002"),
        collector_name="phase3a-tcou-b",
        hostname=HOSTNAME,
        egress_key=EGRESS_KEY,
        lane="background",
    ),
)


@dataclass
class SharedBudget:
    remaining: int
    lock: Lock

    def reserve(self) -> bool:
        with self.lock:
            if self.remaining <= 0:
                return False
            self.remaining -= 1
            return True


@dataclass(frozen=True)
class WorkerResult:
    name: str
    attempted: int
    succeeded: int
    failed: int
    throttles: tuple[tuple[int, int, int | None, str], ...]


def worker(engine, identity: CollectorIdentity, budget: SharedBudget) -> WorkerResult:
    attempted = succeeded = failed = 0
    throttles: list[tuple[int, int, int | None, str]] = []
    try:
        while budget.reserve():
            with engine.begin() as conn:
                heartbeat_collector(conn, collector_uuid=identity.collector_uuid)
                replenish_detailed_bootstrap(
                    conn,
                    target_depth=TARGET_DEPTH,
                    max_soldier_id=max(COHORT_IDS),
                    allowed_soldier_ids=COHORT_IDS,
                )

            result = collect_one_detailed_job(
                engine,
                identity=identity,
                request_interval_seconds=REQUEST_INTERVAL_SECONDS,
                lease_seconds=120,
                timeout_seconds=15.0,
                retry_after_seconds=300,
            )
            if result is None:
                raise RuntimeError(
                    f"{identity.collector_name} reserved a global attempt but found no claimable job"
                )

            attempted += 1
            if isinstance(result, CollectedJob):
                succeeded += 1
            elif isinstance(result, FailedJob):
                failed += 1
                if result.http_status in {403, 429} or result.error_class == "battlelog_throttle":
                    throttles.append(
                        (result.job_id, result.soldier_id, result.http_status, result.error_class)
                    )
            else:
                raise RuntimeError(f"unexpected collector result: {type(result)!r}")
    finally:
        with engine.begin() as conn:
            stop_collector(conn, collector_uuid=identity.collector_uuid)

    return WorkerResult(identity.collector_name, attempted, succeeded, failed, tuple(throttles))


def main() -> None:
    engine = create_engine(os.environ["BF4PS_DATABASE_URL"])
    collector_uuids = [identity.collector_uuid for identity in IDENTITIES]
    collector_names = [identity.collector_name for identity in IDENTITIES]

    with engine.connect() as conn:
        db = conn.execute(text("SELECT current_database()")).scalar_one()
        recovery = conn.execute(text("SELECT pg_is_in_recovery()")).scalar_one()
        revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        queue = conn.execute(text("""
            SELECT job_id, soldier_id, status
            FROM collection_jobs
            WHERE resource = 'detailed' AND lane = 'background'
            ORDER BY job_id
        """)).mappings().all()
        conflicts = conn.execute(text("""
            SELECT collector_uuid, collector_name
            FROM collectors
            WHERE collector_uuid = ANY(:uuids)
               OR (retired_at IS NULL AND lower(collector_name) = ANY(:names))
        """), {
            "uuids": collector_uuids,
            "names": [name.lower() for name in collector_names],
        }).mappings().all()
        cohort = conn.execute(text("""
            SELECT s.soldier_id, s.platform, s.current_name,
                   cs.detailed_state, cs.detailed_last_attempt_at,
                   cs.detailed_last_success_at, dsc.source_fetched_at
            FROM soldiers AS s
            JOIN collection_state AS cs ON cs.soldier_id = s.soldier_id
            LEFT JOIN detailed_stats_current AS dsc ON dsc.soldier_id = s.soldier_id
            WHERE s.soldier_id = ANY(:ids)
            ORDER BY s.soldier_id
        """), {"ids": list(COHORT_IDS)}).mappings().all()

    if "test" not in db.lower():
        raise SystemExit(f"REFUSING: not a test database: {db}")
    if recovery:
        raise SystemExit("REFUSING: database is in recovery")
    if revision != EXPECTED_REVISION:
        raise SystemExit(f"REFUSING: expected Alembic {EXPECTED_REVISION}, found {revision}")
    if queue:
        raise SystemExit("REFUSING: detailed/background queue is not empty")
    if conflicts:
        raise SystemExit(f"REFUSING: frozen collector identities already exist: {conflicts}")
    if len(cohort) != len(COHORT_IDS) or {int(row["soldier_id"]) for row in cohort} != set(COHORT_IDS):
        raise SystemExit("REFUSING: frozen Phase 3A cohort is incomplete")
    if any(row["detailed_state"] != "never_attempted" for row in cohort):
        raise SystemExit("REFUSING: frozen Phase 3A cohort is no longer pristine")
    if any(row["source_fetched_at"] is not None for row in cohort):
        raise SystemExit("REFUSING: frozen Phase 3A cohort already has detailed current data")

    counts = {platform: 0 for platform in EXPECTED_PLATFORM_COUNTS}
    for row in cohort:
        counts[row["platform"]] += 1
    if counts != EXPECTED_PLATFORM_COUNTS:
        raise SystemExit(f"REFUSING: platform mix changed: {counts}")

    print("===== BF4PS PHASE 3A CONCURRENT COLLECTOR LIVE RUN =====\n")
    print(f"database:        {db}")
    print(f"recovery:        {recovery}")
    print(f"alembic:         {revision}")
    print(f"cohort:          {list(COHORT_IDS)}")
    print(f"platform mix:    {counts}")
    print(f"collectors:      {[identity.collector_name for identity in IDENTITIES]}")
    print(f"shared egress:   {EGRESS_KEY}")
    print(f"request interval:{REQUEST_INTERVAL_SECONDS:.1f}s")
    print(f"target depth:    {TARGET_DEPTH}")
    print(f"GLOBAL attempts: {MAX_ATTEMPTS}")
    print("queue empty:     PASS")
    print("cohort pristine: PASS")

    for identity in IDENTITIES:
        with engine.begin() as conn:
            control = register_collector(
                conn,
                identity=identity,
                software_version="phase3a-concurrent-live-validation",
            )
        if not control.may_claim:
            raise RuntimeError(f"{identity.collector_name} is disabled or drained")

    budget = SharedBudget(MAX_ATTEMPTS, Lock())
    results: list[WorkerResult] = []
    print("\nUnleashing two bounded collectors...\n")
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(worker, engine, identity, budget) for identity in IDENTITIES]
        for future in as_completed(futures):
            results.append(future.result())

    with engine.connect() as conn:
        final_cohort = conn.execute(text("""
            SELECT s.soldier_id, s.platform, s.current_name,
                   cs.detailed_state, cs.detailed_last_attempt_at,
                   cs.detailed_last_success_at, dsc.source_fetched_at
            FROM soldiers AS s
            JOIN collection_state AS cs ON cs.soldier_id = s.soldier_id
            LEFT JOIN detailed_stats_current AS dsc ON dsc.soldier_id = s.soldier_id
            WHERE s.soldier_id = ANY(:ids)
            ORDER BY s.soldier_id
        """), {"ids": list(COHORT_IDS)}).mappings().all()
        remaining_jobs = conn.execute(text("""
            SELECT job_id, soldier_id, status, eligible_at, attempt_count,
                   collector_uuid, last_error_class, last_error_at
            FROM collection_jobs
            WHERE resource = 'detailed'
              AND lane = 'background'
              AND soldier_id = ANY(:ids)
            ORDER BY job_id
        """), {"ids": list(COHORT_IDS)}).mappings().all()
        collectors = conn.execute(text("""
            SELECT collector_uuid, collector_name, heartbeat_state,
                   enabled, drained, current_job_id
            FROM collectors
            WHERE collector_uuid = ANY(:uuids)
            ORDER BY collector_name
        """), {"uuids": collector_uuids}).mappings().all()
        events = conn.execute(text("""
            SELECT event_id, occurred_at, collector_uuid, collector_name_snapshot,
                   job_id, soldier_id, platform, event_type, attempt_number,
                   result, http_status, error_class, lease_token
            FROM collection_events
            WHERE collector_uuid = ANY(:uuids)
              AND soldier_id = ANY(:ids)
              AND resource = 'detailed'
              AND lane = 'background'
            ORDER BY event_id
        """), {"uuids": collector_uuids, "ids": list(COHORT_IDS)}).mappings().all()
        gate = conn.execute(text("""
            SELECT egress_key, next_request_at, updated_at
            FROM request_gates
            WHERE egress_key = :egress_key
        """), {"egress_key": EGRESS_KEY}).mappings().one_or_none()

    attempted = sum(result.attempted for result in results)
    succeeded = sum(result.succeeded for result in results)
    failed = sum(result.failed for result in results)
    throttles = [item for result in results for item in result.throttles]
    event_throttles = [row for row in events if row["http_status"] in {403, 429} or row["error_class"] == "battlelog_throttle"]
    attempted_soldiers = [int(row["soldier_id"]) for row in events if row["event_type"] in {"collection_success", "collection_failure"}]

    print("===== WORKER RESULTS =====")
    for result in sorted(results, key=lambda value: value.name):
        print(
            f"{result.name:<18} attempted={result.attempted} "
            f"success={result.succeeded} failed={result.failed} throttles={len(result.throttles)}"
        )
    print(f"GLOBAL attempted: {attempted}/{MAX_ATTEMPTS}")
    print(f"GLOBAL success:   {succeeded}")
    print(f"GLOBAL failed:    {failed}")

    print("\n===== THROTTLE WATCH =====")
    print(f"403/429/throttle results: {len(throttles)}")
    print(f"persisted throttle events:{len(event_throttles)}")
    if event_throttles:
        for row in event_throttles:
            print(
                f"THROTTLE event={row['event_id']} collector={row['collector_name_snapshot']} "
                f"soldier={row['soldier_id']} http={row['http_status']} class={row['error_class']}"
            )
    else:
        print("Battlelog throttle signals: NONE")

    print("\n===== COLLECTION EVENTS =====")
    for row in events:
        print(
            f"event={row['event_id']} collector={row['collector_name_snapshot']:<18} "
            f"soldier={row['soldier_id']:<4} {row['platform']:<8} "
            f"type={row['event_type']:<18} attempt={row['attempt_number']} "
            f"result={row['result']} http={row['http_status']} class={row['error_class']}"
        )

    print("\n===== FINAL COHORT STATE =====")
    for row in final_cohort:
        print(
            f"soldier={row['soldier_id']:<6} {row['platform']:<8} {row['current_name']!r:<22} "
            f"state={row['detailed_state']} last_success={row['detailed_last_success_at']}"
        )

    if attempted != MAX_ATTEMPTS:
        raise RuntimeError(f"expected exactly {MAX_ATTEMPTS} global attempts, got {attempted}")
    if succeeded + failed != MAX_ATTEMPTS:
        raise RuntimeError("success/failure totals do not equal global attempt ceiling")
    if len(attempted_soldiers) != MAX_ATTEMPTS or len(set(attempted_soldiers)) != MAX_ATTEMPTS:
        raise RuntimeError("collection event ledger does not show exactly 12 unique attempted soldiers")
    if set(attempted_soldiers) != set(COHORT_IDS):
        raise RuntimeError("collection event ledger escaped or missed the frozen cohort")
    if any(row["heartbeat_state"] != "unknown" for row in collectors):
        raise RuntimeError("one or more collectors did not stop cleanly")
    if any(not row["enabled"] or row["drained"] for row in collectors):
        raise RuntimeError("runtime changed operator controls")
    if any(row["current_job_id"] is not None for row in collectors):
        raise RuntimeError("collector retained current_job_id after stop")
    if len(throttles) != len(event_throttles):
        raise RuntimeError("runtime throttle results disagree with persisted throttle events")
    if gate is None:
        raise RuntimeError("shared request gate row was not created")

    attempted_states = {"success", "temporary_failure", "unavailable"}
    if any(row["detailed_state"] not in attempted_states for row in final_cohort):
        raise RuntimeError("not every frozen cohort soldier reached an attempted state")

    print("\n===== FINAL VALIDATION =====")
    print("exact global 12-attempt ceiling: PASS")
    print("12 unique frozen soldiers:       PASS")
    print("shared request gate exists:       PASS")
    print("both collectors clean stop:       PASS")
    print("operator controls preserved:      PASS")
    print("throttle evidence reconciled:     PASS")

    if failed == 0:
        if remaining_jobs:
            raise RuntimeError("all-success cohort left detailed/background queue rows")
        if any(row["detailed_state"] != "success" for row in final_cohort):
            raise RuntimeError("all-success result disagrees with collection_state")
        if any(row["source_fetched_at"] is None for row in final_cohort):
            raise RuntimeError("successful cohort is missing detailed current data")
        print("all collections successful:       PASS")
        print("cohort queue finalized:            PASS")
    else:
        print(f"persisted source failures:         {failed}")
        print(f"recoverable queue rows:            {len(remaining_jobs)}")

    print("\nNo cleanup performed; Phase 3A live evidence is intentionally retained.")
    print("BF4PS PHASE 3A CONCURRENT COLLECTOR LIVE RUN: PASS")


if __name__ == "__main__":
    main()
