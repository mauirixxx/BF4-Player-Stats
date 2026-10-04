#!/usr/bin/env python3
"""Validate the committed Phase 3E round-three frozen cohort against the test database.

Read-only: no queue write, collector registration, job claim, state mutation, or
Battlelog request is performed.
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

EXPECTED_DATABASE = "bf4_playerstats_test"
EXPECTED_DB_HOST = "mak-db-02.bf4statusbot.com"
EXPECTED_REVISION = "0003_request_gates"
PLATFORMS = ("pc", "ps4", "xboxone")
PER_PLATFORM = 40


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
    soldier_stmt = text("""
        SELECT s.soldier_id,
               s.persona_id,
               s.platform,
               s.current_name,
               cs.detailed_state,
               cs.detailed_last_attempt_at,
               cs.detailed_last_success_at,
               dsc.soldier_id AS detailed_current_soldier_id,
               cj.job_id AS detailed_job_id
        FROM soldiers AS s
        LEFT JOIN collection_state AS cs
               ON cs.soldier_id = s.soldier_id
        LEFT JOIN detailed_stats_current AS dsc
               ON dsc.soldier_id = s.soldier_id
        LEFT JOIN collection_jobs AS cj
               ON cj.soldier_id = s.soldier_id
              AND cj.resource = 'detailed'
        WHERE s.soldier_id IN :soldier_ids
        ORDER BY s.platform, s.soldier_id
    """).bindparams(bindparam("soldier_ids", expanding=True))

    with engine.connect() as conn:
        target = conn.execute(text("""
            SELECT current_database() AS database_name,
                   pg_is_in_recovery() AS recovery,
                   current_setting('transaction_read_only') AS read_only
        """)).mappings().one()
        revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        rows = conn.execute(
            soldier_stmt,
            {"soldier_ids": list(COHORT_SOLDIER_IDS)},
        ).mappings().all()

    rows_by_id = {int(row["soldier_id"]): row for row in rows}
    expected_platform = {
        int(soldier_id): platform
        for platform, soldier_ids in COHORT_BY_PLATFORM.items()
        for soldier_id in soldier_ids
    }
    found_ids = set(rows_by_id)
    expected_ids = set(COHORT_SOLDIER_IDS)
    platform_counts = Counter(str(row["platform"]) for row in rows)

    missing_ids = sorted(expected_ids - found_ids)
    unexpected_ids = sorted(found_ids - expected_ids)
    platform_mismatches = [
        soldier_id
        for soldier_id, row in rows_by_id.items()
        if str(row["platform"]) != expected_platform[soldier_id]
    ]
    missing_state = [
        soldier_id for soldier_id, row in rows_by_id.items()
        if row["detailed_state"] is None
    ]
    non_pristine = [
        soldier_id for soldier_id, row in rows_by_id.items()
        if row["detailed_state"] != "never_attempted"
        or row["detailed_last_attempt_at"] is not None
        or row["detailed_last_success_at"] is not None
        or row["detailed_current_soldier_id"] is not None
        or row["detailed_job_id"] is not None
    ]

    checks = {
        "expected BF4PS test database": target["database_name"] == EXPECTED_DATABASE,
        "writable PostgreSQL primary": not target["recovery"] and target["read_only"] == "off",
        "expected Alembic head": revision == EXPECTED_REVISION,
        "exactly 120 frozen soldiers found": len(rows) == GLOBAL_ATTEMPT_CEILING
            and not missing_ids and not unexpected_ids,
        "exact frozen platform assignment": not platform_mismatches
            and platform_counts == Counter({p: PER_PLATFORM for p in PLATFORMS}),
        "collection-state rows present": not missing_state,
        "round-three cohort still pristine": not non_pristine,
    }

    print("===== BF4PS PHASE 3E ROUND-THREE FROZEN-COHORT PREFLIGHT =====\n")
    print("READ-ONLY FROZEN MANIFEST VALIDATION")
    print("No queue write, collector registration, job claim, state mutation, or Battlelog request is performed.\n")
    print(f"database:       {target['database_name']}")
    print(f"recovery:       {target['recovery']}")
    print(f"read only:      {target['read_only']}")
    print(f"alembic:        {revision}")
    print(f"frozen cohort:  {len(COHORT_SOLDIER_IDS)}")
    print(f"rows found:     {len(rows)}")
    print(f"global ceiling: {GLOBAL_ATTEMPT_CEILING}\n")

    print("===== PLATFORM COUNTS =====")
    for platform in PLATFORMS:
        print(f"{platform:<8} {platform_counts[platform]}/{PER_PLATFORM}")

    if missing_ids:
        print(f"\nmissing soldier IDs: {missing_ids}")
    if unexpected_ids:
        print(f"unexpected soldier IDs: {unexpected_ids}")
    if platform_mismatches:
        print(f"platform mismatches: {platform_mismatches}")
    if missing_state:
        print(f"missing collection_state rows: {missing_state}")
    if non_pristine:
        print(f"non-pristine round-three soldiers: {non_pristine}")

    print("\n===== SAFETY DECISION =====")
    for label, ok in checks.items():
        print(f"{label:<42} {'PASS' if ok else 'FAIL'}")
    print("external Battlelog requests:               0")
    print("database writes:                           0")

    if all(checks.values()):
        print("\nPHASE 3E ROUND-THREE FROZEN-COHORT PREFLIGHT: PASS")
        return 0
    print("\nPHASE 3E ROUND-THREE FROZEN-COHORT PREFLIGHT: FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())
