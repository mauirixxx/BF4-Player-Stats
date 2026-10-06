#!/usr/bin/env python3
"""Read-only Phase 5A preflight for the frozen 10/10/10 weapon cohort.

This script performs zero database writes and zero Battlelog requests. It
selects exactly ten pristine weapon candidates per supported platform using a
deterministic soldier_id ordering and prints the proposed frozen cohort.
Unrelated historical jobs outside the selected cohort are preserved and do
not block the preflight.
"""
from __future__ import annotations

from collections import Counter

from sqlalchemy import bindparam, text

from bf4ps.db import make_engine

EXPECTED_DATABASE = "bf4_playerstats_test"
EXPECTED_REVISION = "0003_request_gates"
PLATFORMS = ("pc", "ps4", "xboxone")
PER_PLATFORM = 10


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    suffix = f"  {detail}" if detail else ""
    print(f"{label:<72} {status}{suffix}")
    if not condition:
        raise AssertionError(f"{label}: {detail or 'condition was false'}")


def main() -> int:
    print("===== BF4PS PHASE 5A MULTIPLATFORM WEAPON PREFLIGHT =====")
    print("scope: read-only deterministic census / 10 PC + 10 PS4 + 10 Xbox One")
    print("database writes: 0")
    print("Battlelog requests: 0")

    engine = make_engine()
    candidates = []

    with engine.connect() as conn:
        db = conn.execute(text("SELECT current_database()")).scalar_one()
        revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        recovery = bool(conn.execute(text("SELECT pg_is_in_recovery()")).scalar_one())
        read_only = conn.execute(text("SELECT current_setting('transaction_read_only')")).scalar_one()
        check("target database is bf4_playerstats_test", db == EXPECTED_DATABASE, str(db))
        check("target is writable primary", not recovery and read_only == "off", f"recovery={recovery} read_only={read_only}")
        check("Alembic revision is frozen Phase 5A revision", revision == EXPECTED_REVISION, str(revision))

        for platform in PLATFORMS:
            rows = conn.execute(text("""
                SELECT s.soldier_id, s.persona_id, s.current_name, s.platform
                FROM soldiers s
                JOIN collection_state cs ON cs.soldier_id = s.soldier_id
                WHERE s.platform = :platform
                  AND cs.detailed_state = 'success'
                  AND cs.weapons_state = 'never_attempted'
                  AND cs.vehicles_state = 'never_attempted'
                  AND NOT EXISTS (
                      SELECT 1 FROM soldier_weapon_stats sw
                      WHERE sw.soldier_id = s.soldier_id
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM soldier_vehicle_stats sv
                      WHERE sv.soldier_id = s.soldier_id
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM collection_jobs j
                      WHERE j.soldier_id = s.soldier_id
                        AND j.resource IN ('weapons', 'vehicles')
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM collection_events e
                      WHERE e.soldier_id = s.soldier_id
                        AND e.resource IN ('weapons', 'vehicles')
                  )
                ORDER BY s.soldier_id
                LIMIT :limit
            """), {"platform": platform, "limit": PER_PLATFORM}).mappings().all()
            check(f"{platform} has {PER_PLATFORM} pristine full-stats candidates", len(rows) == PER_PLATFORM, str(len(rows)))
            candidates.extend(rows)

        soldier_ids = [int(row["soldier_id"]) for row in candidates]
        cohort_jobs_stmt = text("""
            SELECT count(*)
            FROM collection_jobs
            WHERE soldier_id IN :soldier_ids
              AND resource IN ('weapons', 'vehicles')
        """).bindparams(bindparam("soldier_ids", expanding=True))
        cohort_jobs = conn.execute(cohort_jobs_stmt, {"soldier_ids": soldier_ids}).scalar_one()
        check("selected cohort has no existing weapon/vehicle jobs", int(cohort_jobs) == 0, str(cohort_jobs))

    counts = Counter(str(row["platform"]) for row in candidates)
    check("frozen cohort contains exactly 30 soldiers", len(candidates) == 30, str(len(candidates)))
    check("frozen platform split is exactly 10/10/10", counts == Counter({"pc": 10, "ps4": 10, "xboxone": 10}), str(dict(counts)))
    check("frozen soldier IDs are unique", len({int(row["soldier_id"]) for row in candidates}) == 30)

    print("\n===== PROPOSED FROZEN COHORT =====")
    for platform in PLATFORMS:
        print(f"\n[{platform}]")
        platform_rows = [row for row in candidates if row["platform"] == platform]
        for number, row in enumerate(platform_rows, 1):
            print(
                f"{number:02d}. soldier={row['soldier_id']} persona={row['persona_id']} "
                f"name={row['current_name']!r} platform={row['platform']}"
            )

    print("\n===== ACCEPTANCE =====")
    print("database writes: 0")
    print("Battlelog requests: 0")
    print("PHASE 5A MULTIPLATFORM WEAPON PREFLIGHT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
