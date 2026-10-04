#!/usr/bin/env python3
"""Read-only Phase 3E cohort/capacity preflight."""
from __future__ import annotations

import os
import sys
from collections import Counter

from sqlalchemy import create_engine, text

EXPECTED_DB = "bf4_playerstats_test"
EXPECTED_ALEMBIC = "0003_request_gates"
TARGET_MINIMUM = 120
PLATFORMS = ("pc", "ps4", "xboxone")


def main() -> int:
    url = os.environ.get("BF4PS_DATABASE_URL")
    if not url:
        print("REFUSING: BF4PS_DATABASE_URL is not set")
        return 2

    engine = create_engine(url)
    with engine.connect() as conn:
        target = conn.execute(text("""
            SELECT current_database() AS database_name,
                   pg_is_in_recovery() AS recovery,
                   current_setting('transaction_read_only') AS read_only
        """)).mappings().one()
        alembic = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()

        rows = conn.execute(text("""
            SELECT s.soldier_id, s.platform, s.persona_id, s.current_name
            FROM soldiers AS s
            JOIN collection_state AS cs ON cs.soldier_id = s.soldier_id
            LEFT JOIN detailed_stats_current AS dsc ON dsc.soldier_id = s.soldier_id
            WHERE s.platform IN ('pc', 'ps4', 'xboxone')
              AND cs.detailed_state = 'never_attempted'
              AND cs.detailed_last_attempt_at IS NULL
              AND cs.detailed_last_success_at IS NULL
              AND dsc.soldier_id IS NULL
              AND NOT EXISTS (
                  SELECT 1
                  FROM collection_jobs AS cj
                  WHERE cj.soldier_id = s.soldier_id
                    AND cj.resource = 'detailed'
              )
            ORDER BY s.platform, s.soldier_id
        """)).mappings().all()

    counts = Counter(r["platform"] for r in rows)
    balanced = min((counts[p] for p in PLATFORMS), default=0) * len(PLATFORMS)
    target_each = TARGET_MINIMUM // len(PLATFORMS)

    print("===== BF4PS PHASE 3E COHORT / CAPACITY PREFLIGHT =====\n")
    print("READ-ONLY PREFLIGHT")
    print("No queue write, collector registration, feeder pass, job claim, or Battlelog request is performed.\n")
    print(f"database:       {target['database_name']}")
    print(f"recovery:       {target['recovery']}")
    print(f"read only:      {target['read_only']}")
    print(f"alembic:        {alembic}")
    print("resource/lane:  detailed/background")
    print(f"design minimum: {TARGET_MINIMUM} attempts ({target_each}/{target_each}/{target_each})\n")

    print("===== PRISTINE DETAILED CAPACITY =====")
    for p in PLATFORMS:
        print(f"{p:<8} {counts[p]}")
    print(f"total:    {len(rows)}")
    print(f"balanced mixed-platform capacity: {balanced}\n")

    print("===== FIRST DESIGN-SIZED COHORT =====")
    selected = []
    for p in PLATFORMS:
        selected.extend([r for r in rows if r["platform"] == p][:target_each])
    for r in selected:
        print(f"soldier={r['soldier_id']:<7} {r['platform']:<8} persona={str(r['persona_id']):<13} {r['current_name']!r}")

    checks = {
        "expected BF4PS test database": target["database_name"] == EXPECTED_DB,
        "writable PostgreSQL primary": not target["recovery"] and target["read_only"] == "off",
        "expected Alembic head": alembic == EXPECTED_ALEMBIC,
        f"at least {target_each} pristine PC soldiers": counts["pc"] >= target_each,
        f"at least {target_each} pristine PS4 soldiers": counts["ps4"] >= target_each,
        f"at least {target_each} pristine Xbox One soldiers": counts["xboxone"] >= target_each,
        f"at least {TARGET_MINIMUM} balanced candidates": balanced >= TARGET_MINIMUM,
    }

    print("\n===== SAFETY DECISION =====")
    for label, ok in checks.items():
        print(f"{label:<48} {'PASS' if ok else 'FAIL'}")
    print("external Battlelog requests:                     0")
    print("database writes:                                 0")

    if all(checks.values()):
        print("\nPHASE 3E COHORT / CAPACITY PREFLIGHT: PASS")
        return 0
    print("\nPHASE 3E COHORT / CAPACITY PREFLIGHT: FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())
