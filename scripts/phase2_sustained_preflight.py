#!/usr/bin/env python3
"""Read-only preflight for the Phase 2 sustained automatic runtime test."""

from __future__ import annotations

import os

from sqlalchemy import create_engine, text

EXPECTED_REVISION = "0003_request_gates"
COHORT_SIZE = 10
TARGET_DEPTH = 1
MAX_JOBS = 10

# This query intentionally mirrors bounded_feeder.replenish_detailed_bootstrap()
# eligibility. Keep it synchronized with the production feeder rather than
# inventing a parallel definition of bootstrap eligibility.
ELIGIBLE_SQL = text("""
    SELECT s.soldier_id, s.persona_id, s.platform, s.current_name,
           dsc.source_fetched_at AS current_source_fetched_at,
           cs.detailed_last_success_at AS last_success_at,
           cs.detailed_state AS collection_state
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
    ORDER BY s.soldier_id ASC
    LIMIT :cohort_size
""")


def main() -> None:
    engine = create_engine(os.environ["BF4PS_DATABASE_URL"])

    with engine.connect() as conn:
        db = conn.execute(text("SELECT current_database()" )).scalar_one()
        recovery = conn.execute(text("SELECT pg_is_in_recovery()" )).scalar_one()
        revision = conn.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()
        queue = conn.execute(text("""
            SELECT job_id, soldier_id, status, eligible_at
            FROM collection_jobs
            WHERE resource = 'detailed'
              AND lane = 'background'
            ORDER BY job_id
        """)).mappings().all()
        candidates = conn.execute(
            ELIGIBLE_SQL, {"cohort_size": COHORT_SIZE}
        ).mappings().all()

    if "test" not in db.lower():
        raise SystemExit(f"REFUSING: not a test database: {db}")
    if recovery:
        raise SystemExit("REFUSING: database is in recovery")
    if revision != EXPECTED_REVISION:
        raise SystemExit(
            f"REFUSING: expected Alembic {EXPECTED_REVISION}, found {revision}"
        )
    if queue:
        raise SystemExit("REFUSING: detailed/background queue is not empty")
    if len(candidates) != COHORT_SIZE:
        raise SystemExit(
            f"REFUSING: expected {COHORT_SIZE} eligible soldiers, "
            f"found {len(candidates)}"
        )

    max_soldier_id = int(candidates[-1]["soldier_id"])

    print("===== BF4PS PHASE 2 SUSTAINED RUNTIME PREFLIGHT =====\n")
    print("READ-ONLY PREFLIGHT")
    print("No feeder pass, queue write, job claim, or Battlelog request is performed.\n")
    print(f"database:       {db}")
    print(f"recovery:       {recovery}")
    print(f"alembic:        {revision}")
    print(f"target_depth:   {TARGET_DEPTH}")
    print(f"max_jobs:       {MAX_JOBS}")
    print(f"cohort_size:    {COHORT_SIZE}")
    print(f"max_soldier_id: {max_soldier_id}")
    print("resource/lane:  detailed/background")

    print("\n===== EXISTING DETAILED/BACKGROUND QUEUE =====")
    print("(empty)")

    print("\n===== EXPECTED SUSTAINED COHORT =====")
    for row in candidates:
        print(
            f"soldier={row['soldier_id']:<7} {row['platform']:<8} "
            f"persona={row['persona_id']:<13} {row['current_name']!r}"
        )
        print(
            f"         detailed_current={row['current_source_fetched_at']} "
            f"last_success={row['last_success_at']} "
            f"state={row['collection_state']}"
        )

    print("\n===== SAFETY DECISION =====")
    print("test database:                         PASS")
    print("writable primary:                      PASS")
    print("expected Alembic head:                 PASS")
    print("existing detailed/background queue:    EMPTY")
    print(f"exactly {COHORT_SIZE} bounded candidates found: PASS")
    print(f"derived hard soldier boundary:         {max_soldier_id}")
    print("working queue target depth:             1")
    print("hard collection-attempt ceiling:       10")
    print("external requests:                     0")
    print("database writes:                        0")
    print("\nPHASE 2 SUSTAINED RUNTIME PREFLIGHT: PASS")


if __name__ == "__main__":
    main()
