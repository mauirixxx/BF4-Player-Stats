#!/usr/bin/env python3
"""Generate the deterministic Phase 3E 40/40/40 endurance manifest.

Read-only: this script prints a Python manifest fragment for review/commit. It
never mutates BF4PS state and never performs a Battlelog request.
"""
from __future__ import annotations

import os
import sys
from collections import Counter
from urllib.parse import urlsplit

from sqlalchemy import create_engine, text

EXPECTED_DATABASE = "bf4_playerstats_test"
EXPECTED_DB_HOST = "mak-db-02.bf4statusbot.com"
EXPECTED_REVISION = "0003_request_gates"
PLATFORMS = ("pc", "ps4", "xboxone")
PER_PLATFORM = 40
GLOBAL_ATTEMPT_CEILING = 120


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
    with engine.connect() as conn:
        target = conn.execute(text("""
            SELECT current_database() AS database_name,
                   pg_is_in_recovery() AS recovery,
                   current_setting('transaction_read_only') AS read_only
        """)).mappings().one()
        revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
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
                    SELECT 1 FROM collection_jobs AS cj
                    WHERE cj.soldier_id = s.soldier_id
                      AND cj.resource = 'detailed'
              )
            ORDER BY s.platform, s.soldier_id
        """)).mappings().all()

    counts = Counter(str(row["platform"]) for row in rows)
    selected = []
    for platform in PLATFORMS:
        selected.extend(row for row in rows if row["platform"] == platform)[:PER_PLATFORM]

    checks = {
        "expected BF4PS test database": target["database_name"] == EXPECTED_DATABASE,
        "writable PostgreSQL primary": not target["recovery"] and target["read_only"] == "off",
        "expected Alembic head": revision == EXPECTED_REVISION,
        "exact 40/40/40 selection": len(selected) == GLOBAL_ATTEMPT_CEILING
            and Counter(str(row["platform"]) for row in selected)
                == Counter({p: PER_PLATFORM for p in PLATFORMS}),
        "unique soldier IDs": len({int(row["soldier_id"]) for row in selected}) == len(selected),
    }

    print("===== BF4PS PHASE 3E MANIFEST FREEZE =====\n")
    print("READ-ONLY MANIFEST GENERATOR")
    print("No queue write, collector registration, job claim, or Battlelog request is performed.\n")
    for platform in PLATFORMS:
        print(f"pristine {platform:<8} {counts[platform]}")
    print(f"selected:        {len(selected)}")
    print(f"global ceiling:  {GLOBAL_ATTEMPT_CEILING}\n")

    print("COHORT = (")
    for row in selected:
        name = str(row["current_name"]).replace("\\", "\\\\").replace("'", "\\'")
        print(
            f"    ({int(row['soldier_id'])}, '{row['platform']}', "
            f"{int(row['persona_id'])}, '{name}'),"
        )
    print(")")

    print("\n===== SAFETY DECISION =====")
    for label, ok in checks.items():
        print(f"{label:<42} {'PASS' if ok else 'FAIL'}")
    print("external Battlelog requests:               0")
    print("database writes:                           0")

    if all(checks.values()):
        print("\nPHASE 3E MANIFEST FREEZE: PASS")
        return 0
    print("\nPHASE 3E MANIFEST FREEZE: FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())
