#!/usr/bin/env python3
"""Read-only preflight for the first Phase 2 automatic collector run."""

from __future__ import annotations

import os

from sqlalchemy import create_engine, text

TARGET_DEPTH = 3
MAX_JOBS = 3
MAX_SOLDIER_ID = 6
LANE = "background"
RESOURCE = "detailed"


def main() -> None:
    engine = create_engine(os.environ["BF4PS_DATABASE_URL"])

    with engine.connect() as conn:
        db = conn.execute(text("SELECT current_database()" )).scalar_one()
        recovery = conn.execute(text("SELECT pg_is_in_recovery()" )).scalar_one()
        if "test" not in db.lower():
            raise SystemExit(f"REFUSING: not a test database: {db}")
        if recovery:
            raise SystemExit("REFUSING: database is in recovery")

        revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()

        queue = conn.execute(
            text(
                """
                SELECT job_id, soldier_id, resource, lane, priority_class,
                       reason, status, eligible_at
                FROM collection_jobs
                WHERE resource = :resource
                  AND lane = :lane
                ORDER BY job_id
                """
            ),
            {"resource": RESOURCE, "lane": LANE},
        ).mappings().all()

        # Mirror bounded_feeder.py eligibility exactly. collection_state is one
        # row per soldier with resource-prefixed columns. detailed_stats_current
        # records its source observation time as source_fetched_at; observed_at
        # belongs to detailed_stats_history.
        candidates = conn.execute(
            text(
                """
                SELECT s.soldier_id, s.persona_id, s.platform, s.current_name,
                       dsc.source_fetched_at AS current_source_fetched_at,
                       cs.detailed_last_success_at AS last_success_at,
                       cs.detailed_state AS collection_state
                FROM soldiers AS s
                JOIN collection_state AS cs
                  ON cs.soldier_id = s.soldier_id
                LEFT JOIN detailed_stats_current AS dsc
                  ON dsc.soldier_id = s.soldier_id
                WHERE s.soldier_id <= :max_soldier_id
                  AND s.platform IN ('pc', 'ps4', 'xboxone')
                  AND cs.detailed_state = 'never_attempted'
                  AND NOT EXISTS (
                      SELECT 1
                      FROM collection_jobs AS j
                      WHERE j.soldier_id = s.soldier_id
                        AND j.resource = 'detailed'
                  )
                ORDER BY s.soldier_id ASC
                LIMIT :target_depth
                """
            ),
            {"max_soldier_id": MAX_SOLDIER_ID, "target_depth": TARGET_DEPTH},
        ).mappings().all()

    print("===== BF4PS PHASE 2 SINGLE-NODE AUTOMATIC PREFLIGHT =====\n")
    print("READ-ONLY PREFLIGHT")
    print("No feeder pass, queue write, job claim, or Battlelog request is performed.\n")
    print(f"database:       {db}")
    print(f"recovery:       {recovery}")
    print(f"alembic:        {revision}")
    print(f"target_depth:   {TARGET_DEPTH}")
    print(f"max_jobs:       {MAX_JOBS}")
    print(f"max_soldier_id: {MAX_SOLDIER_ID}")
    print(f"resource/lane:  {RESOURCE}/{LANE}")

    print("\n===== EXISTING DETAILED/BACKGROUND QUEUE =====")
    if not queue:
        print("(empty)")
    else:
        for row in queue:
            print(
                f"job={row['job_id']} soldier={row['soldier_id']} "
                f"{row['priority_class']} reason={row['reason']} "
                f"status={row['status']} eligible={row['eligible_at']}"
            )

    print("\n===== EXPECTED NEW BOOTSTRAP COHORT =====")
    if not candidates:
        print("(none)")
    else:
        for row in candidates:
            print(
                f"soldier={row['soldier_id']:<6} {row['platform']:<8} "
                f"persona={row['persona_id']!s:<14} {row['current_name']!r}"
            )
            print(
                f"         detailed_current={row['current_source_fetched_at']} "
                f"last_success={row['last_success_at']} "
                f"state={row['collection_state']}"
            )

    print("\n===== SAFETY DECISION =====")
    if queue:
        print("AUTOMATIC RUN: NOT READY")
        print("Reason: detailed/background queue is not empty; inspect it before proceeding.")
        raise SystemExit(2)

    if len(candidates) != TARGET_DEPTH:
        print("AUTOMATIC RUN: NOT READY")
        print(
            f"Reason: expected exactly {TARGET_DEPTH} eligible bootstrap candidates, "
            f"found {len(candidates)}."
        )
        raise SystemExit(2)

    print("existing detailed/background queue empty: PASS")
    print(f"exactly {TARGET_DEPTH} bounded candidates found: PASS")
    print("external requests: 0")
    print("database writes:    0")
    print("\nPHASE 2 SINGLE-NODE AUTOMATIC PREFLIGHT: PASS")


if __name__ == "__main__":
    main()
