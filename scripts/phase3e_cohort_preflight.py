#!/usr/bin/env python3
"""Read-only Phase 3E cohort/capacity preflight.

Inspects the BF4PS test database and reports pristine mixed-platform capacity for
Phase 3E without materializing work, registering collectors, or making external
requests.
"""
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
        db = conn.execute(text("SELECT current_database()" )).scalar_one()
        recovery = conn.execute(text("SELECT pg_is_in_recovery()" )).scalar_one()
        alembic = conn.execute(text("SELECT version_num FROM alembic_version" )).scalar_one()

        # Schema names are taken from docs/database-schema-reference.md and the
        # current Alembic migrations. A pristine candidate has no detailed
        # collection state and has never appeared in a detailed collection job.
        rows = conn.execute(text("""
            SELECT s.id, s.platform, s.persona_id, s.player_name
            FROM soldiers AS s
            WHERE s.platform IN ('pc', 'ps4', 'xboxone')
              AND NOT EXISTS (
                  SELECT 1
                  FROM collection_state AS cs
                  WHERE cs.soldier_id = s.id
                    AND cs.resource = 'detailed'
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM collection_jobs AS cj
                  WHERE cj.soldier_id = s.id
                    AND cj.resource = 'detailed'
              )
            ORDER BY s.platform, s.id
        """)).mappings().all()

    counts = Counter(r["platform"] for r in rows)
    balanced = min((counts[p] for p in PLATFORMS), default=0) * len(PLATFORMS)
    target_each = TARGET_MINIMUM // len(PLATFORMS)

    print("===== BF4PS PHASE 3E COHORT / CAPACITY PREFLIGHT =====\n")
    print("READ-ONLY PREFLIGHT")
    print("No queue write, collector registration, feeder pass, job claim, or Battlelog request is performed.\n")
    print(f"database:       {db}")
    print(f"recovery:       {recovery}")
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
        print(f"soldier={r['id']:<7} {r['platform']:<8} persona={str(r['persona_id']):<13} {r['player_name']!r}")

    checks = {
        "expected BF4PS test database": db == EXPECTED_DB,
        "writable PostgreSQL primary": not recovery,
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
