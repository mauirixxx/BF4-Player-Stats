#!/usr/bin/env python3
"""Read-only Phase 4A census and deterministic 90-PC cohort preview."""
from __future__ import annotations

import os
from collections import Counter

from sqlalchemy import create_engine, text

EXPECTED_DB = "bf4_playerstats_test"
EXPECTED_ALEMBIC = "0003_request_gates"
COHORT_SIZE = 90


def assert_target(conn) -> None:
    database = conn.execute(text("SELECT current_database()" )).scalar_one()
    revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    if database != EXPECTED_DB or revision != EXPECTED_ALEMBIC:
        raise RuntimeError(
            f"REFUSING target database={database!r} alembic={revision!r}; "
            f"expected {EXPECTED_DB!r}/{EXPECTED_ALEMBIC!r}"
        )


def main() -> int:
    url = os.environ.get("BF4PS_DATABASE_URL")
    if not url:
        raise SystemExit("REFUSING: BF4PS_DATABASE_URL is not set")

    engine = create_engine(url, pool_pre_ping=True)
    with engine.connect() as conn:
        assert_target(conn)

        candidates = conn.execute(text("""
            SELECT s.soldier_id, s.persona_id, s.current_name, s.platform
            FROM soldiers AS s
            JOIN collection_state AS cs ON cs.soldier_id = s.soldier_id
            WHERE s.platform = 'pc'
              AND cs.detailed_state = 'never_attempted'
              AND NOT EXISTS (
                    SELECT 1
                    FROM collection_jobs AS j
                    WHERE j.soldier_id = s.soldier_id
                      AND j.resource = 'detailed'
              )
            ORDER BY s.soldier_id ASC
            LIMIT :limit
        """), {"limit": COHORT_SIZE}).mappings().all()

        eligible_count = int(conn.execute(text("""
            SELECT COUNT(*)
            FROM soldiers AS s
            JOIN collection_state AS cs ON cs.soldier_id = s.soldier_id
            WHERE s.platform = 'pc'
              AND cs.detailed_state = 'never_attempted'
              AND NOT EXISTS (
                    SELECT 1
                    FROM collection_jobs AS j
                    WHERE j.soldier_id = s.soldier_id
                      AND j.resource = 'detailed'
              )
        """)).scalar_one())

        state_rows = conn.execute(text("""
            SELECT detailed_state, COUNT(*) AS n
            FROM collection_state
            GROUP BY detailed_state
            ORDER BY detailed_state
        """)).all()

        counters = {
            "soldiers": int(conn.execute(text("SELECT COUNT(*) FROM soldiers")).scalar_one()),
            "current": int(conn.execute(text("SELECT COUNT(*) FROM detailed_stats_current")).scalar_one()),
            "history": int(conn.execute(text("SELECT COUNT(*) FROM detailed_stats_history")).scalar_one()),
            "events": int(conn.execute(text("SELECT COUNT(*) FROM collection_events")).scalar_one()),
            "jobs": int(conn.execute(text("SELECT COUNT(*) FROM collection_jobs")).scalar_one()),
            "detailed_background_jobs": int(conn.execute(text("""
                SELECT COUNT(*) FROM collection_jobs
                WHERE resource='detailed' AND lane='background'
            """)).scalar_one()),
        }
        max_event = conn.execute(text("SELECT MAX(event_id) FROM collection_events")).scalar_one()
        collectors = conn.execute(text("""
            SELECT collector_name, hostname, egress_key, enabled, drained,
                   heartbeat_state, current_job_id, retired_at
            FROM collectors
            ORDER BY hostname, collector_name
        """)).mappings().all()
        throttle = conn.execute(text("""
            SELECT http_status, COUNT(*) AS n
            FROM collection_events
            WHERE http_status IN (403,429)
            GROUP BY http_status ORDER BY http_status
        """)).all()

    print("===== BF4PS PHASE 4A COHORT CENSUS =====")
    print(f"eligible untouched PC soldiers: {eligible_count}")
    print(f"deterministic preview size:     {len(candidates)}/{COHORT_SIZE}")
    print()
    print("Starting database counters:")
    for key, value in counters.items():
        print(f"  {key:<25} {value}")
    print(f"  max_event_id              {max_event}")
    print()
    print("Detailed collection-state distribution:")
    for state, n in state_rows:
        print(f"  {state:<20} {n}")
    print()
    print("Collector registry:")
    for row in collectors:
        print(
            f"  {row['hostname']:<8} {row['collector_name']:<20} "
            f"egress={row['egress_key']!r} enabled={row['enabled']} drained={row['drained']} "
            f"heartbeat={row['heartbeat_state']} current_job={row['current_job_id']} retired={row['retired_at']}"
        )
    print()
    print("Historical 403/429 event counts:")
    if throttle:
        for status, n in throttle:
            print(f"  HTTP {status}: {n}")
    else:
        print("  none")
    print()
    print("Deterministic Phase 4A preview (first 90 eligible PC soldiers):")
    for i, row in enumerate(candidates, 1):
        print(
            f"  {i:02d} soldier={row['soldier_id']} persona={row['persona_id']} "
            f"name={row['current_name']!r} platform={row['platform']}"
        )

    ids = [int(row['soldier_id']) for row in candidates]
    personas = [int(row['persona_id']) for row in candidates]
    names = [str(row['current_name']) for row in candidates]
    checks = [
        ("at least 90 eligible untouched PC soldiers", eligible_count >= COHORT_SIZE),
        ("preview contains exactly 90 soldiers", len(candidates) == COHORT_SIZE),
        ("preview soldier IDs unique", len(ids) == len(set(ids))),
        ("preview persona IDs unique", len(personas) == len(set(personas))),
        ("preview names non-empty", all(name.strip() for name in names)),
        ("preview platforms all PC", all(row['platform'] == 'pc' for row in candidates)),
        ("no detailed/background queue exists at baseline", counters['detailed_background_jobs'] == 0),
        ("no collector currently owns a job", all(row['current_job_id'] is None for row in collectors if row['retired_at'] is None)),
    ]
    print()
    print("Validation:")
    for label, ok in checks:
        print(f"{label:<58} {'PASS' if ok else 'FAIL'}")
    print("database writes: 0")
    print("Battlelog requests: 0")
    passed = all(ok for _, ok in checks)
    print(f"PHASE 4A COHORT CENSUS: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
