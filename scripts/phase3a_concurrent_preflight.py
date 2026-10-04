#!/usr/bin/env python3
"""Read-only preflight for the Phase 3A concurrent collector proof."""

from __future__ import annotations

import os
from uuid import UUID

from sqlalchemy import create_engine, text

EXPECTED_REVISION = "0003_request_gates"
PLATFORMS = ("pc", "ps4", "xboxone")
PER_PLATFORM = 4
COHORT_SIZE = PER_PLATFORM * len(PLATFORMS)
TARGET_DEPTH = 2
MAX_ATTEMPTS = COHORT_SIZE
RESOURCE = "detailed"
LANE = "background"
EGRESS_KEY = "phase3a-concurrent-tcou"
COLLECTORS = (
    (UUID("b2b3ef60-62e8-4d4a-91b0-41a2e2a30001"), "phase3a-tcou-a"),
    (UUID("b2b3ef60-62e8-4d4a-91b0-41a2e2a30002"), "phase3a-tcou-b"),
)


def main() -> None:
    engine = create_engine(os.environ["BF4PS_DATABASE_URL"])

    collector_uuids = [collector_uuid for collector_uuid, _ in COLLECTORS]
    collector_names = [collector_name for _, collector_name in COLLECTORS]

    with engine.connect() as conn:
        db = conn.execute(text("SELECT current_database()")).scalar_one()
        recovery = conn.execute(text("SELECT pg_is_in_recovery()")).scalar_one()
        revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()

        queue = conn.execute(text("""
            SELECT job_id, soldier_id, resource, lane, status,
                   collector_uuid, lease_token, eligible_at
            FROM collection_jobs
            WHERE resource = 'detailed'
              AND lane = 'background'
            ORDER BY job_id
        """)).mappings().all()

        collector_conflicts = conn.execute(text("""
            SELECT collector_uuid, collector_name, hostname, lane, egress_key,
                   enabled, drained, heartbeat_state, current_job_id, retired_at
            FROM collectors
            WHERE collector_uuid = ANY(:collector_uuids)
               OR (retired_at IS NULL AND lower(collector_name) = ANY(:collector_names_lower))
            ORDER BY collector_name, collector_uuid
        """), {
            "collector_uuids": collector_uuids,
            "collector_names_lower": [name.lower() for name in collector_names],
        }).mappings().all()

        rows = conn.execute(text("""
            WITH eligible AS (
                SELECT s.soldier_id, s.persona_id, s.platform, s.current_name,
                       cs.detailed_state,
                       cs.detailed_last_attempt_at,
                       cs.detailed_last_success_at,
                       cs.detailed_next_due_at,
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
                   detailed_state, detailed_last_attempt_at,
                   detailed_last_success_at, detailed_next_due_at,
                   source_fetched_at
            FROM eligible
            WHERE platform_rank <= :per_platform
            ORDER BY CASE platform
                         WHEN 'pc' THEN 1
                         WHEN 'ps4' THEN 2
                         WHEN 'xboxone' THEN 3
                     END,
                     soldier_id ASC
        """), {"per_platform": PER_PLATFORM}).mappings().all()

    print("===== BF4PS PHASE 3A CONCURRENT COLLECTOR PREFLIGHT =====\n")
    print("READ-ONLY PREFLIGHT")
    print("No collector registration, feeder pass, queue write, job claim, or Battlelog request is performed.\n")
    print(f"database:        {db}")
    print(f"recovery:        {recovery}")
    print(f"alembic:         {revision}")
    print(f"resource/lane:   {RESOURCE}/{LANE}")
    print(f"cohort size:     {COHORT_SIZE}")
    print(f"per platform:    {PER_PLATFORM}")
    print(f"target depth:    {TARGET_DEPTH}")
    print(f"global attempts: {MAX_ATTEMPTS}")
    print(f"shared egress:   {EGRESS_KEY}")

    if "test" not in db.lower():
        raise SystemExit(f"REFUSING: not a test database: {db}")
    if recovery:
        raise SystemExit("REFUSING: database is in recovery")
    if revision != EXPECTED_REVISION:
        raise SystemExit(
            f"REFUSING: expected Alembic {EXPECTED_REVISION}, found {revision}"
        )

    print("\n===== FROZEN COLLECTOR IDENTITIES =====")
    for collector_uuid, collector_name in COLLECTORS:
        print(f"{collector_name:<18} {collector_uuid} egress={EGRESS_KEY}")

    print("\n===== EXISTING COLLECTOR IDENTITY CONFLICTS =====")
    if collector_conflicts:
        for row in collector_conflicts:
            print(
                f"uuid={row['collector_uuid']} name={row['collector_name']!r} "
                f"host={row['hostname']!r} lane={row['lane']} egress={row['egress_key']!r} "
                f"enabled={row['enabled']} drained={row['drained']} "
                f"heartbeat={row['heartbeat_state']} current_job={row['current_job_id']} "
                f"retired_at={row['retired_at']}"
            )
    else:
        print("(none)")

    print("\n===== EXISTING DETAILED/BACKGROUND QUEUE =====")
    if queue:
        for row in queue:
            print(
                f"job={row['job_id']} soldier={row['soldier_id']} status={row['status']} "
                f"owner={row['collector_uuid']} lease={row['lease_token']} "
                f"eligible={row['eligible_at']}"
            )
    else:
        print("(empty)")

    print("\n===== PROPOSED FROZEN PHASE 3A COHORT =====")
    counts = {platform: 0 for platform in PLATFORMS}
    for row in rows:
        counts[row["platform"]] += 1
        print(
            f"soldier={row['soldier_id']:<7} {row['platform']:<8} "
            f"persona={row['persona_id']:<13} {row['current_name']!r}"
        )
        print(
            f"         state={row['detailed_state']} "
            f"last_attempt={row['detailed_last_attempt_at']} "
            f"last_success={row['detailed_last_success_at']} "
            f"next_due={row['detailed_next_due_at']} "
            f"current={row['source_fetched_at']}"
        )

    exact_mix = all(counts[platform] == PER_PLATFORM for platform in PLATFORMS)
    exact_size = len(rows) == COHORT_SIZE
    cohort_ids = [int(row["soldier_id"]) for row in rows]
    max_soldier_id = max(cohort_ids, default=None)

    print("\n===== PLATFORM COUNTS =====")
    for platform in PLATFORMS:
        print(f"{platform:<8} {counts[platform]}/{PER_PLATFORM}")

    print("\n===== SAFETY DECISION =====")
    print("test database:                         PASS")
    print("writable primary:                      PASS")
    print("expected Alembic head:                 PASS")
    print(f"existing detailed/background queue:    {'EMPTY' if not queue else 'NOT EMPTY'}")
    print(f"collector identity conflicts:          {'NONE' if not collector_conflicts else 'PRESENT'}")
    print(f"exact 4/4/4 platform mix:              {'PASS' if exact_mix else 'FAIL'}")
    print(f"exactly 12 candidates found:           {'PASS' if exact_size else 'FAIL'}")
    print(f"derived max soldier boundary:          {max_soldier_id}")
    print(f"frozen cohort IDs:                     {cohort_ids}")
    print(f"working queue target depth:            {TARGET_DEPTH}")
    print(f"hard GLOBAL collection-attempt ceiling:{MAX_ATTEMPTS}")
    print("external requests:                     0")
    print("database writes:                       0")

    if queue:
        raise SystemExit("PREFLIGHT FAIL: detailed/background queue is not empty")
    if collector_conflicts:
        raise SystemExit("PREFLIGHT FAIL: frozen Phase 3A collector identities already exist")
    if not exact_mix or not exact_size:
        raise SystemExit("PREFLIGHT FAIL: exact 4 PC / 4 PS4 / 4 Xbox One cohort unavailable")

    print("\nPHASE 3A CONCURRENT COLLECTOR PREFLIGHT: PASS")


if __name__ == "__main__":
    main()
