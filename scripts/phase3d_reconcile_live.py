#!/usr/bin/env python3
"""Read-only global reconciliation for the frozen Phase 3D three-host proof."""
from __future__ import annotations

import os
from collections import Counter, defaultdict
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import create_engine, text

EXPECTED_DATABASE = "bf4_playerstats_test"
EXPECTED_DB_HOST = "mak-db-02.bf4statusbot.com"
EXPECTED_REVISION = "0003_request_gates"
RESOURCE = "detailed"
LANE = "background"
COHORT_IDS = (
    24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35,
    112, 113, 114, 115, 116, 117, 118, 119, 120, 121, 122, 123,
    100, 101, 102, 103, 104, 162, 163, 164, 165, 166, 167, 168,
)
COLLECTORS = {
    UUID("b2b3ef60-62e8-4d4a-91b0-41a2e2a3d001"): ("phase3d-hnl-01", "hnl-01", "phase3d-hnl-01"),
    UUID("b2b3ef60-62e8-4d4a-91b0-41a2e2a3d002"): ("phase3d-kah-01", "kah-01", "phase3d-kah-01"),
    UUID("b2b3ef60-62e8-4d4a-91b0-41a2e2a3d003"): ("phase3d-tcou", "tcou", "phase3d-tcou"),
}


def check(label: str, condition: bool) -> bool:
    print(f"{label:<43} {'PASS' if condition else 'FAIL'}")
    return condition


def main() -> None:
    database_url = os.environ.get("BF4PS_DATABASE_URL")
    if not database_url:
        raise SystemExit("REFUSING: BF4PS_DATABASE_URL is not set")
    parsed = urlsplit(database_url)
    if parsed.hostname != EXPECTED_DB_HOST or parsed.path.lstrip("/") != EXPECTED_DATABASE:
        raise SystemExit("REFUSING: database URL is not the frozen Phase 3D test target")

    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as conn:
        db = conn.execute(text("SELECT current_database()" )).scalar_one()
        recovery = conn.execute(text("SELECT pg_is_in_recovery()" )).scalar_one()
        revision = conn.execute(text("SELECT version_num FROM alembic_version" )).scalar_one()
        jobs = conn.execute(text("""
            SELECT job_id, soldier_id, status, attempt_count, collector_uuid,
                   lease_token, claimed_at, started_at, lease_expires_at
            FROM collection_jobs
            WHERE resource = :resource AND lane = :lane
            ORDER BY job_id
        """), {"resource": RESOURCE, "lane": LANE}).mappings().all()
        events = conn.execute(text("""
            SELECT event_id, collector_uuid, collector_name_snapshot,
                   hostname_snapshot, egress_key_snapshot, job_id, soldier_id,
                   platform, event_type, attempt_number, result, http_status,
                   error_class, lease_token
            FROM collection_events
            WHERE resource = :resource AND lane = :lane
              AND collector_uuid = ANY(:collector_uuids)
              AND event_type IN ('collection_success', 'collection_failure')
            ORDER BY event_id
        """), {
            "resource": RESOURCE,
            "lane": LANE,
            "collector_uuids": list(COLLECTORS),
        }).mappings().all()
        collectors = conn.execute(text("""
            SELECT collector_uuid, collector_name, hostname, egress_key,
                   enabled, drained, heartbeat_state, current_job_id, retired_at
            FROM collectors
            WHERE collector_uuid = ANY(:collector_uuids)
            ORDER BY collector_name
        """), {"collector_uuids": list(COLLECTORS)}).mappings().all()
        gates = conn.execute(text("""
            SELECT egress_key, next_request_at, updated_at
            FROM request_gates
            WHERE egress_key = ANY(:egress_keys)
            ORDER BY egress_key
        """), {"egress_keys": [item[2] for item in COLLECTORS.values()]}).mappings().all()
        states = conn.execute(text("""
            SELECT soldier_id, detailed_state, detailed_last_attempt_at,
                   detailed_last_success_at, detailed_consecutive_failures,
                   detailed_last_error_class, detailed_last_error_message
            FROM collection_state
            WHERE soldier_id = ANY(:cohort_ids)
            ORDER BY soldier_id
        """), {"cohort_ids": list(COHORT_IDS)}).mappings().all()

    print("===== BF4PS PHASE 3D GLOBAL RECONCILIATION =====")
    print("\nREAD-ONLY POST-RUN VALIDATION")
    print("No queue, collector, event, state, gate, or Battlelog mutation is performed.\n")
    print(f"database:       {db}")
    print(f"recovery:       {recovery}")
    print(f"alembic:        {revision}")
    print(f"resource/lane:  {RESOURCE}/{LANE}")
    print(f"frozen cohort:  {len(COHORT_IDS)}")
    print(f"event rows:     {len(events)}")

    by_collector = Counter(row["collector_uuid"] for row in events)
    successes = [row for row in events if row["event_type"] == "collection_success" and row["result"] == "success"]
    failures = [row for row in events if row["event_type"] == "collection_failure" or row["result"] != "success"]
    throttles = [row for row in events if row["http_status"] in {403, 429} or row["error_class"] == "battlelog_throttle"]
    event_soldiers = [int(row["soldier_id"]) for row in events if row["soldier_id"] is not None]
    event_jobs = [int(row["job_id"]) for row in events if row["job_id"] is not None]

    print("\n===== COLLECTOR DISTRIBUTION =====")
    for uuid, (name, host, egress) in COLLECTORS.items():
        rows = [row for row in events if row["collector_uuid"] == uuid]
        ok_snapshot = all(
            row["collector_name_snapshot"] == name
            and row["hostname_snapshot"] == host
            and row["egress_key_snapshot"] == egress
            for row in rows
        )
        print(f"{host:<8} {name:<18} attempts={len(rows):2d} snapshots={'PASS' if ok_snapshot else 'FAIL'}")

    print("\n===== QUEUE =====")
    if jobs:
        for row in jobs:
            print(f"job={row['job_id']} soldier={row['soldier_id']} status={row['status']} attempt={row['attempt_count']} owner={row['collector_uuid']}")
    else:
        print("(empty — all detailed/background jobs finalized)")

    print("\n===== REQUEST GATES =====")
    for row in gates:
        print(f"{row['egress_key']:<18} next={row['next_request_at']} updated={row['updated_at']}")

    print("\n===== GLOBAL VALIDATION =====")
    results = []
    results.append(check("expected BF4PS test database:", db == EXPECTED_DATABASE))
    results.append(check("writable PostgreSQL primary:", not recovery))
    results.append(check("expected Alembic head:", revision == EXPECTED_REVISION))
    results.append(check("exactly 36 terminal attempt events:", len(events) == 36))
    results.append(check("exactly 36 collection successes:", len(successes) == 36))
    results.append(check("zero collection failures:", len(failures) == 0))
    results.append(check("zero 403/429/throttle signals:", len(throttles) == 0))
    results.append(check("exactly 36 unique soldiers:", len(event_soldiers) == 36 and len(set(event_soldiers)) == 36))
    results.append(check("exact frozen cohort covered:", set(event_soldiers) == set(COHORT_IDS)))
    results.append(check("exactly 36 unique logical jobs:", len(event_jobs) == 36 and len(set(event_jobs)) == 36))
    results.append(check("attempt numbers all exactly one:", all(row["attempt_number"] == 1 for row in events)))
    results.append(check("all three collectors attempted 12:", set(by_collector) == set(COLLECTORS) and all(by_collector[u] == 12 for u in COLLECTORS)))
    results.append(check("all event snapshots match frozen hosts:", all(
        row["collector_uuid"] in COLLECTORS
        and (row["collector_name_snapshot"], row["hostname_snapshot"], row["egress_key_snapshot"]) == COLLECTORS[row["collector_uuid"]]
        for row in events
    )))
    results.append(check("detailed/background queue finalized:", len(jobs) == 0))
    results.append(check("all three collector rows present:", len(collectors) == 3 and {r["collector_uuid"] for r in collectors} == set(COLLECTORS)))
    results.append(check("all collectors cleanly stopped:", len(collectors) == 3 and all(r["heartbeat_state"] == "unknown" and r["current_job_id"] is None for r in collectors)))
    results.append(check("operator controls preserved:", len(collectors) == 3 and all(r["enabled"] and not r["drained"] and r["retired_at"] is None for r in collectors)))
    results.append(check("all three request gates materialized:", len(gates) == 3 and {r["egress_key"] for r in gates} == {v[2] for v in COLLECTORS.values()}))
    results.append(check("36 detailed states successful:", len(states) == 36 and all(r["detailed_state"] == "success" and r["detailed_last_success_at"] is not None and r["detailed_consecutive_failures"] == 0 for r in states)))

    print("\nBattlelog requests performed by reconciliation: 0")
    if all(results):
        print("BF4PS PHASE 3D GLOBAL RECONCILIATION: PASS")
    else:
        raise SystemExit("BF4PS PHASE 3D GLOBAL RECONCILIATION: FAIL")


if __name__ == "__main__":
    main()
