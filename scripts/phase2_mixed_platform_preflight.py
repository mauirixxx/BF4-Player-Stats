#!/usr/bin/env python3
"""Read-only preflight for the Phase 2 mixed-platform sustained cohort."""

from __future__ import annotations

import os

from sqlalchemy import create_engine, text

EXPECTED_REVISION = "0003_request_gates"
PER_PLATFORM = 3
PLATFORMS = ("pc", "ps4", "xboxone")
TARGET_DEPTH = 1
MAX_JOBS = PER_PLATFORM * len(PLATFORMS)


def main() -> None:
    engine = create_engine(os.environ["BF4PS_DATABASE_URL"])

    with engine.connect() as conn:
        db = conn.execute(text("SELECT current_database()")).scalar_one()
        recovery = conn.execute(text("SELECT pg_is_in_recovery()")).scalar_one()
        revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        queue = conn.execute(text("""
            SELECT job_id, soldier_id, status
            FROM collection_jobs
            WHERE resource = 'detailed'
              AND lane = 'background'
            ORDER BY job_id
        """)).mappings().all()

        rows = conn.execute(text("""
            WITH eligible AS (
                SELECT s.soldier_id, s.persona_id, s.platform, s.current_name,
                       cs.detailed_state,
                       cs.detailed_last_success_at,
                       dsc.source_fetched_at,
                       row_number() OVER (
                           PARTITION BY s.platform
                           ORDER BY s.soldier_id ASC
                       ) AS platform_rank
                FROM soldiers AS s
                JOIN collection_state AS cs
                  ON cs.soldier_id = s.soldier_id
                LEFT JOIN detailed_stats_current AS dsc
                  ON dsc.soldier_id = s.soldier_id
                WHERE s.platform IN ('pc', 'ps4', 'xboxone')
                  AND cs.detailed_state = 'never_attempted'
                  AND NOT EXISTS (
                      SELECT 1
                      FROM collection_jobs AS j
                      WHERE j.soldier_id = s.soldier_id
                        AND j.resource = 'detailed'
                  )
            )
            SELECT soldier_id, persona_id, platform, current_name,
                   detailed_state, detailed_last_success_at, source_fetched_at
            FROM eligible
            WHERE platform_rank <= :per_platform
            ORDER BY CASE platform
                         WHEN 'pc' THEN 1
                         WHEN 'ps4' THEN 2
                         WHEN 'xboxone' THEN 3
                     END,
                     soldier_id ASC
        """), {"per_platform": PER_PLATFORM}).mappings().all()

    print("===== BF4PS PHASE 2 MIXED-PLATFORM PREFLIGHT =====\n")
    print("READ-ONLY PREFLIGHT")
    print("No feeder pass, queue write, job claim, or Battlelog request is performed.\n")
    print(f"database:       {db}")
    print(f"recovery:       {recovery}")
    print(f"alembic:        {revision}")
    print(f"per platform:   {PER_PLATFORM}")
    print(f"cohort size:    {MAX_JOBS}")
    print(f"target_depth:   {TARGET_DEPTH}")
    print(f"max_jobs:       {MAX_JOBS}")
    print("platforms:      pc, ps4, xboxone")

    if "test" not in db.lower():
        raise SystemExit(f"REFUSING: not a test database: {db}")
    if recovery:
        raise SystemExit("REFUSING: database is in recovery")
    if revision != EXPECTED_REVISION:
        raise SystemExit(
            f"REFUSING: expected Alembic {EXPECTED_REVISION}, found {revision}"
        )

    print("\n===== EXISTING DETAILED/BACKGROUND QUEUE =====")
    if queue:
        for row in queue:
            print(
                f"job={row['job_id']} soldier={row['soldier_id']} "
                f"status={row['status']}"
            )
    else:
        print("(empty)")

    print("\n===== EXPECTED MIXED-PLATFORM COHORT =====")
    counts = {platform: 0 for platform in PLATFORMS}
    for row in rows:
        counts[row["platform"]] += 1
        print(
            f"soldier={row['soldier_id']:<7} {row['platform']:<8} "
            f"persona={row['persona_id']:<13} {row['current_name']!r}"
        )
        print(
            f"         detailed_current={row['source_fetched_at']} "
            f"last_success={row['detailed_last_success_at']} "
            f"state={row['detailed_state']}"
        )

    exact_mix = all(counts[p] == PER_PLATFORM for p in PLATFORMS)
    exact_size = len(rows) == MAX_JOBS
    max_soldier_id = max((int(row["soldier_id"]) for row in rows), default=None)

    print("\n===== PLATFORM COUNTS =====")
    for platform in PLATFORMS:
        print(f"{platform:<8} {counts[platform]}/{PER_PLATFORM}")

    print("\n===== SAFETY DECISION =====")
    print("test database:                      PASS")
    print("writable primary:                   PASS")
    print("expected Alembic head:              PASS")
    print(f"existing detailed/background queue: {'EMPTY' if not queue else 'NOT EMPTY'}")
    print(f"exact 3/3/3 platform mix:           {'PASS' if exact_mix else 'FAIL'}")
    print(f"exactly 9 candidates found:         {'PASS' if exact_size else 'FAIL'}")
    print(f"derived max soldier boundary:       {max_soldier_id}")
    print(f"working queue target depth:         {TARGET_DEPTH}")
    print(f"hard collection-attempt ceiling:    {MAX_JOBS}")
    print("external requests:                  0")
    print("database writes:                    0")

    if queue:
        raise SystemExit("PREFLIGHT FAIL: detailed/background queue is not empty")
    if not exact_mix or not exact_size:
        raise SystemExit("PREFLIGHT FAIL: exact 3 PC / 3 PS4 / 3 Xbox One cohort unavailable")

    print("\nPHASE 2 MIXED-PLATFORM PREFLIGHT: PASS")


if __name__ == "__main__":
    main()
