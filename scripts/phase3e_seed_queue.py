#!/usr/bin/env python3
"""Seed the first bounded Phase 3E round-three actionable working set.

This is intentionally NOT a full 120-job queue preparation step. The frozen
Phase 3E design requires normal bounded feeder replenishment, so this harness
performs exactly one production feeder pass against the committed round-three
cohort. No Battlelog request is performed.
"""
from __future__ import annotations

import os
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import bindparam, create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parent))
from phase3e_frozen_cohort_round3 import (  # noqa: E402
    COHORT_BY_PLATFORM,
    COHORT_SOLDIER_IDS,
    GLOBAL_ATTEMPT_CEILING,
)
from bf4ps.bounded_feeder import replenish_detailed_bootstrap  # noqa: E402

EXPECTED_DATABASE = "bf4_playerstats_test"
EXPECTED_DB_HOST = "mak-db-02.bf4statusbot.com"
EXPECTED_REVISION = "0003_request_gates"
RESOURCE = "detailed"
LANE = "background"
TARGET_DEPTH = 6


def main() -> int:
    database_url = os.environ.get("BF4PS_DATABASE_URL")
    if not database_url:
        print("REFUSING: BF4PS_DATABASE_URL is not set")
        return 2

    parsed = urlsplit(database_url)
    if parsed.hostname != EXPECTED_DB_HOST or parsed.path.lstrip("/") != EXPECTED_DATABASE:
        print("REFUSING: database URL is not the frozen Phase 3E test target")
        return 2

    engine = create_engine(database_url, pool_pre_ping=True)
    ids = list(COHORT_SOLDIER_IDS)
    max_soldier_id = max(ids)

    cohort_stmt = text("""
        SELECT s.soldier_id, s.platform,
               cs.detailed_state,
               cs.detailed_last_attempt_at,
               cs.detailed_last_success_at,
               dsc.soldier_id AS current_stats_id
        FROM soldiers AS s
        JOIN collection_state AS cs ON cs.soldier_id = s.soldier_id
        LEFT JOIN detailed_stats_current AS dsc ON dsc.soldier_id = s.soldier_id
        WHERE s.soldier_id IN :soldier_ids
        ORDER BY s.soldier_id
    """).bindparams(bindparam("soldier_ids", expanding=True))

    queue_stmt = text("""
        SELECT job_id, soldier_id, status, attempt_count, priority_class, reason
        FROM collection_jobs
        WHERE resource = 'detailed'
          AND lane = 'background'
          AND soldier_id IN :soldier_ids
        ORDER BY job_id
    """).bindparams(bindparam("soldier_ids", expanding=True))

    foreign_queue_stmt = text("""
        SELECT job_id, soldier_id, status
        FROM collection_jobs
        WHERE resource = 'detailed'
          AND lane = 'background'
          AND soldier_id NOT IN :soldier_ids
        ORDER BY job_id
    """).bindparams(bindparam("soldier_ids", expanding=True))

    event_count_stmt = text("""
        SELECT COUNT(*)
        FROM collection_events
        WHERE resource = 'detailed'
          AND lane = 'background'
          AND soldier_id IN :soldier_ids
          AND event_type IN ('collection_success', 'collection_failure')
    """).bindparams(bindparam("soldier_ids", expanding=True))

    with engine.begin() as conn:
        target = conn.execute(text("""
            SELECT current_database() AS database_name,
                   pg_is_in_recovery() AS recovery,
                   current_setting('transaction_read_only') AS read_only
        """)).mappings().one()
        revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        rows = conn.execute(cohort_stmt, {"soldier_ids": ids}).mappings().all()
        queue_before = conn.execute(queue_stmt, {"soldier_ids": ids}).mappings().all()
        foreign_before = conn.execute(foreign_queue_stmt, {"soldier_ids": ids}).mappings().all()
        terminal_before = int(conn.execute(event_count_stmt, {"soldier_ids": ids}).scalar_one())

        expected_platform = {
            int(soldier_id): platform
            for platform, soldier_ids in COHORT_BY_PLATFORM.items()
            for soldier_id in soldier_ids
        }
        row_ids = {int(row["soldier_id"]) for row in rows}
        platform_counts = Counter(str(row["platform"]) for row in rows)
        pristine = all(
            row["detailed_state"] == "never_attempted"
            and row["detailed_last_attempt_at"] is None
            and row["detailed_last_success_at"] is None
            and row["current_stats_id"] is None
            and str(row["platform"]) == expected_platform[int(row["soldier_id"])]
            for row in rows
        )

        prechecks = {
            "expected BF4PS test database": target["database_name"] == EXPECTED_DATABASE,
            "writable PostgreSQL primary": not target["recovery"] and target["read_only"] == "off",
            "expected Alembic head": revision == EXPECTED_REVISION,
            "exact frozen cohort present": row_ids == set(ids) and len(rows) == GLOBAL_ATTEMPT_CEILING,
            "exact 40/40/40 platform mix": platform_counts == Counter({"pc": 40, "ps4": 40, "xboxone": 40}),
            "frozen cohort pristine": pristine,
            "frozen cohort queue empty": not queue_before,
            "no foreign detailed/background queue": not foreign_before,
            "no prior frozen terminal attempts": terminal_before == 0,
        }

        if not all(prechecks.values()):
            print("===== BF4PS PHASE 3E ROUND-THREE INITIAL QUEUE SEED =====\n")
            print("REFUSING: pre-mutation safety check failed\n")
            for label, ok in prechecks.items():
                print(f"{label:<42} {'PASS' if ok else 'FAIL'}")
            return 1

        result = replenish_detailed_bootstrap(
            conn,
            target_depth=TARGET_DEPTH,
            max_soldier_id=max_soldier_id,
            allowed_soldier_ids=ids,
            max_total_attempts=GLOBAL_ATTEMPT_CEILING,
        )

        queue_after = conn.execute(queue_stmt, {"soldier_ids": ids}).mappings().all()
        foreign_after = conn.execute(foreign_queue_stmt, {"soldier_ids": ids}).mappings().all()

        checks = {
            "pre-mutation safety checks": all(prechecks.values()),
            "production bounded feeder used": True,
            "actionable before exactly zero": result.actionable_before == 0,
            "initial target depth exactly six": result.target_depth == TARGET_DEPTH,
            "exactly six jobs created": result.created == TARGET_DEPTH,
            "actionable after exactly six": result.actionable_after == TARGET_DEPTH,
            "exactly six frozen queue rows": len(queue_after) == TARGET_DEPTH,
            "all seeded jobs pending attempt zero": all(
                row["status"] == "pending" and int(row["attempt_count"]) == 0
                for row in queue_after
            ),
            "bootstrap queue semantics preserved": all(
                row["priority_class"] == "bootstrap" and row["reason"] == "bootstrap"
                for row in queue_after
            ),
            "no work outside frozen cohort": not foreign_after,
        }

    print("===== BF4PS PHASE 3E ROUND-THREE INITIAL QUEUE SEED =====\n")
    print("DATABASE-MUTATING BOUNDED FEEDER PASS")
    print("No collector registration, job claim, or Battlelog request is performed.\n")
    print(f"database:        {target['database_name']}")
    print(f"alembic:         {revision}")
    print(f"resource/lane:   {RESOURCE}/{LANE}")
    print(f"frozen cohort:   {GLOBAL_ATTEMPT_CEILING}")
    print(f"target depth:    {TARGET_DEPTH}")
    print(f"created:         {result.created}")
    print(f"actionable after:{result.actionable_after}\n")

    print("===== SEEDED JOBS =====")
    for row in queue_after:
        print(
            f"job={int(row['job_id']):<5} soldier={int(row['soldier_id']):<5} "
            f"status={row['status']} attempt={int(row['attempt_count'])}"
        )

    print("\n===== FINAL VALIDATION =====")
    for label, ok in checks.items():
        print(f"{label:<42} {'PASS' if ok else 'FAIL'}")
    print("external Battlelog requests:               0")
    print("database writes:                           bounded feeder only")

    if all(checks.values()):
        print("\nPHASE 3E ROUND-THREE INITIAL QUEUE SEED: PASS")
        print("Queue is intentionally only six jobs deep; do NOT materialize all 120.")
        return 0
    print("\nPHASE 3E ROUND-THREE INITIAL QUEUE SEED: FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())
