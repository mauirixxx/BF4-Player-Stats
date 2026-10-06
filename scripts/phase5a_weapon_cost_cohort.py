#!/usr/bin/env python3
"""Bounded live Phase 5A weapon cost characterization against the test database.

Default scope is exactly ten pristine weapon candidates and at most ten
Battlelog weapon requests. The existing PostgreSQL request gate remains the
pacing authority for every request.
"""
from __future__ import annotations

import argparse
import statistics

from sqlalchemy import bindparam, text

from bf4ps.collection_jobs import enqueue_job
from bf4ps.db import make_engine
from bf4ps.weapon_collector import CollectorIdentity, collect_one_weapon_job

EXPECTED_DATABASE = "bf4_playerstats_test"
EXPECTED_REVISION = "0003_request_gates"
COLLECTOR_NAME = "phase3e-tcou"
HOSTNAME = "tcou"
REQUEST_INTERVAL_SECONDS = 5.0
DEFAULT_COHORT_SIZE = 10
MAX_COHORT_SIZE = 30


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    suffix = f"  {detail}" if detail else ""
    print(f"{label:<70} {status}{suffix}")
    if not condition:
        raise AssertionError(f"{label}: {detail or 'condition was false'}")


def percentile(values: list[int], fraction: float) -> int:
    ordered = sorted(values)
    if not ordered:
        return 0
    index = round((len(ordered) - 1) * fraction)
    return ordered[index]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cohort-size", type=int, default=DEFAULT_COHORT_SIZE)
    args = parser.parse_args()
    cohort_size = args.cohort_size
    if not 1 <= cohort_size <= MAX_COHORT_SIZE:
        parser.error(f"--cohort-size must be between 1 and {MAX_COHORT_SIZE}")

    print("===== BF4PS PHASE 5A WEAPON COST COHORT =====")
    print(f"scope: exactly {cohort_size} pristine soldiers / at most {cohort_size} Battlelog weapon requests")
    print(f"request gate interval: {REQUEST_INTERVAL_SECONDS:.1f}s")
    engine = make_engine()

    with engine.connect() as conn:
        db = conn.execute(text("SELECT current_database()" )).scalar_one()
        revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        recovery = bool(conn.execute(text("SELECT pg_is_in_recovery()" )).scalar_one())
        read_only = conn.execute(text("SELECT current_setting('transaction_read_only')" )).scalar_one()
        check("target database is bf4_playerstats_test", db == EXPECTED_DATABASE, str(db))
        check("target is writable primary", not recovery and read_only == "off", f"recovery={recovery} read_only={read_only}")
        check("Alembic revision is frozen Phase 5A revision", revision == EXPECTED_REVISION, str(revision))

        collector = conn.execute(text("""
            SELECT collector_uuid, collector_name, hostname, egress_key, lane,
                   enabled, drained, current_job_id, retired_at
            FROM collectors
            WHERE collector_name=:collector_name AND retired_at IS NULL
        """), {"collector_name": COLLECTOR_NAME}).mappings().one()
        check("tcou collector identity is exact", collector["hostname"] == HOSTNAME, str(dict(collector)))
        check("tcou collector is enabled and undrained", bool(collector["enabled"]) and not bool(collector["drained"]))
        check("tcou collector is idle", collector["current_job_id"] is None)

        candidates = conn.execute(text("""
            SELECT s.soldier_id, s.persona_id, s.current_name, s.platform
            FROM soldiers s
            JOIN collection_state cs ON cs.soldier_id=s.soldier_id
            WHERE cs.detailed_state='success'
              AND cs.weapons_state='never_attempted'
              AND NOT EXISTS (SELECT 1 FROM soldier_weapon_stats sw WHERE sw.soldier_id=s.soldier_id)
              AND NOT EXISTS (SELECT 1 FROM collection_jobs j WHERE j.soldier_id=s.soldier_id AND j.resource='weapons')
              AND NOT EXISTS (SELECT 1 FROM collection_events e WHERE e.soldier_id=s.soldier_id AND e.resource='weapons')
            ORDER BY s.soldier_id
            LIMIT :limit
        """), {"limit": cohort_size}).mappings().all()
        check(f"{cohort_size} pristine weapon candidates exist", len(candidates) == cohort_size, str(len(candidates)))

    soldier_ids = [int(c["soldier_id"]) for c in candidates]
    print("\n===== COHORT =====")
    for number, candidate in enumerate(candidates, 1):
        print(
            f"{number:02d}. soldier={candidate['soldier_id']} persona={candidate['persona_id']} "
            f"name={candidate['current_name']!r} platform={candidate['platform']}"
        )

    with engine.begin() as conn:
        job_ids = []
        for candidate in candidates:
            job_ids.append(enqueue_job(
                conn,
                soldier_id=int(candidate["soldier_id"]),
                resource="weapons",
                lane="background",
                priority_class="bootstrap",
                reason="phase5a_weapon_cost_cohort",
                priority_value=1000000,
            ))
    print(f"\nqueued weapon jobs: {job_ids}")

    identity = CollectorIdentity(
        collector_uuid=collector["collector_uuid"],
        collector_name=str(collector["collector_name"]),
        hostname=str(collector["hostname"]),
        egress_key=str(collector["egress_key"]),
        lane=str(collector["lane"]),
    )

    lifecycle_results = []
    print("\n===== LIVE COLLECTION =====")
    for attempt in range(1, cohort_size + 1):
        result = collect_one_weapon_job(
            engine,
            identity=identity,
            request_interval_seconds=REQUEST_INTERVAL_SECONDS,
            allowed_soldier_ids=soldier_ids,
            max_total_attempts=cohort_size,
        )
        check(f"attempt {attempt:02d} produced one lifecycle result", result is not None, repr(result))
        lifecycle_results.append(result)
        print(f"attempt {attempt:02d}: {result!r}")

    event_stmt = text("""
        SELECT event_id, job_id, soldier_id, persona_id, platform, event_type,
               result, http_status, error_class, duration_ms, metadata
        FROM collection_events
        WHERE resource='weapons'
          AND soldier_id IN :soldier_ids
        ORDER BY event_id
    """).bindparams(bindparam("soldier_ids", expanding=True))

    row_stmt = text("""
        SELECT soldier_id, count(*) AS weapon_rows
        FROM soldier_weapon_stats
        WHERE soldier_id IN :soldier_ids
        GROUP BY soldier_id
    """).bindparams(bindparam("soldier_ids", expanding=True))

    job_stmt = text("""
        SELECT job_id, soldier_id, status, attempt_count, collector_uuid,
               lease_token, eligible_at, last_error_class
        FROM collection_jobs
        WHERE resource='weapons'
          AND soldier_id IN :soldier_ids
        ORDER BY soldier_id
    """).bindparams(bindparam("soldier_ids", expanding=True))

    state_stmt = text("""
        SELECT soldier_id, weapons_state, weapons_consecutive_failures,
               weapons_last_error_class, weapons_last_error_message
        FROM collection_state
        WHERE soldier_id IN :soldier_ids
        ORDER BY soldier_id
    """).bindparams(bindparam("soldier_ids", expanding=True))

    with engine.connect() as conn:
        events = conn.execute(event_stmt, {"soldier_ids": soldier_ids}).mappings().all()
        row_counts = {int(r["soldier_id"]): int(r["weapon_rows"]) for r in conn.execute(row_stmt, {"soldier_ids": soldier_ids}).mappings()}
        jobs = conn.execute(job_stmt, {"soldier_ids": soldier_ids}).mappings().all()
        states = {int(r["soldier_id"]): r for r in conn.execute(state_stmt, {"soldier_ids": soldier_ids}).mappings()}

    check("exactly one weapon attempt event per cohort soldier", len(events) == cohort_size, str(len(events)))
    event_by_soldier = {int(e["soldier_id"]): e for e in events}
    check("all cohort soldiers have an event", set(event_by_soldier) == set(soldier_ids))
    job_by_soldier = {int(j["soldier_id"]): j for j in jobs}

    successes = 0
    failures = 0
    response_bytes: list[int] = []
    durations: list[int] = []
    successful_rows: list[int] = []

    print("\n===== PER-SOLDIER EVIDENCE =====")
    for candidate in candidates:
        soldier_id = int(candidate["soldier_id"])
        event = event_by_soldier[soldier_id]
        state = states[soldier_id]
        metadata = event["metadata"] or {}
        rows = row_counts.get(soldier_id, 0)
        result = event["result"]
        duration = int(event["duration_ms"] or 0)
        measured_bytes = int(metadata.get("response_bytes", 0) or 0)

        check(f"soldier {soldier_id} lifecycle event is valid", event["event_type"] in ("collection_success", "collection_failure"), str(dict(event)))
        if result == "success":
            successes += 1
            check(f"soldier {soldier_id} state is success", state["weapons_state"] == "success", str(dict(state)))
            check(f"soldier {soldier_id} persisted weapon rows", rows > 0, str(rows))
            check(f"soldier {soldier_id} success job finalized", soldier_id not in job_by_soldier)
            check(f"soldier {soldier_id} response bytes recorded", measured_bytes > 0, str(metadata))
            check(f"soldier {soldier_id} row count matches metadata", rows == int(metadata.get("weapon_rows", -1)), f"rows={rows} metadata={metadata}")
            response_bytes.append(measured_bytes)
            durations.append(duration)
            successful_rows.append(rows)
        else:
            failures += 1
            job = job_by_soldier.get(soldier_id)
            check(f"soldier {soldier_id} failure state is temporary", state["weapons_state"] == "temporary_failure", str(dict(state)))
            check(f"soldier {soldier_id} failure persisted no rows", rows == 0, str(rows))
            check(
                f"soldier {soldier_id} retry job is pending and unowned",
                job is not None and job["status"] == "pending" and job["collector_uuid"] is None and job["lease_token"] is None,
                str(dict(job)) if job else "missing",
            )

        print(
            f"soldier={soldier_id} persona={candidate['persona_id']} platform={candidate['platform']} "
            f"result={result} http={event['http_status']} duration_ms={duration} "
            f"bytes={measured_bytes} rows={rows} error={event['error_class']}"
        )

    print("\n===== COST SUMMARY =====")
    print(f"Battlelog weapon requests: {cohort_size}")
    print(f"successes: {successes}")
    print(f"failures: {failures}")
    if response_bytes:
        total_bytes = sum(response_bytes)
        print(f"successful response bytes total: {total_bytes}")
        print(f"successful response bytes mean: {round(statistics.mean(response_bytes))}")
        print(f"successful response bytes median: {round(statistics.median(response_bytes))}")
        print(f"successful response bytes min/max: {min(response_bytes)} / {max(response_bytes)}")
        print(f"successful response bytes p90: {percentile(response_bytes, 0.90)}")
        print(f"successful duration ms mean: {round(statistics.mean(durations))}")
        print(f"successful duration ms median: {round(statistics.median(durations))}")
        print(f"successful duration ms min/max: {min(durations)} / {max(durations)}")
        print(f"successful duration ms p90: {percentile(durations, 0.90)}")
        print(f"successful weapon rows mean: {statistics.mean(successful_rows):.1f}")
        print(f"successful weapon rows min/max: {min(successful_rows)} / {max(successful_rows)}")

    print("\n===== ACCEPTANCE =====")
    print(f"bounded request ceiling: {cohort_size}")
    print(f"observed attempt events: {len(events)}")
    print("PHASE 5A WEAPON COST COHORT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
