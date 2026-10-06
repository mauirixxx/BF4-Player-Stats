#!/usr/bin/env python3
"""Read-only verifier for the frozen Phase 4A 90-PC cohort."""
from __future__ import annotations

import os

from sqlalchemy import bindparam, create_engine, text

from phase4a_cohort import PHASE4A_COHORT, SOLDIER_IDS

EXPECTED_DB = "bf4_playerstats_test"
EXPECTED_ALEMBIC = "0003_request_gates"


def main() -> int:
    url = os.environ.get("BF4PS_DATABASE_URL")
    if not url:
        raise SystemExit("REFUSING: BF4PS_DATABASE_URL is not set")

    engine = create_engine(url, pool_pre_ping=True)
    with engine.connect() as conn:
        database = conn.execute(text("SELECT current_database()" )).scalar_one()
        revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        if database != EXPECTED_DB or revision != EXPECTED_ALEMBIC:
            raise RuntimeError(
                f"REFUSING target database={database!r} alembic={revision!r}; "
                f"expected {EXPECTED_DB!r}/{EXPECTED_ALEMBIC!r}"
            )

        soldier_stmt = text("""
            SELECT soldier_id, persona_id, current_name, platform
            FROM soldiers
            WHERE soldier_id IN :ids
            ORDER BY soldier_id
        """).bindparams(bindparam("ids", expanding=True))
        actual = conn.execute(soldier_stmt, {"ids": SOLDIER_IDS}).all()

        state_stmt = text("""
            SELECT soldier_id, detailed_state, detailed_last_attempt_at,
                   detailed_last_success_at
            FROM collection_state
            WHERE soldier_id IN :ids
            ORDER BY soldier_id
        """).bindparams(bindparam("ids", expanding=True))
        states = conn.execute(state_stmt, {"ids": SOLDIER_IDS}).mappings().all()

        job_stmt = text("""
            SELECT job_id, soldier_id, resource, lane, status, attempt_count,
                   collector_uuid, lease_token
            FROM collection_jobs
            WHERE soldier_id IN :ids
            ORDER BY soldier_id, resource
        """).bindparams(bindparam("ids", expanding=True))
        jobs = conn.execute(job_stmt, {"ids": SOLDIER_IDS}).mappings().all()

    expected = list(PHASE4A_COHORT)
    actual_tuples = [
        (int(r.soldier_id), int(r.persona_id), str(r.current_name), str(r.platform))
        for r in actual
    ]
    state_by_id = {int(r["soldier_id"]): r for r in states}

    identity_exact = actual_tuples == expected
    all_state_rows = len(states) == 90 and set(state_by_id) == set(SOLDIER_IDS)
    all_pristine = all_state_rows and all(
        state_by_id[sid]["detailed_state"] == "never_attempted"
        and state_by_id[sid]["detailed_last_attempt_at"] is None
        and state_by_id[sid]["detailed_last_success_at"] is None
        for sid in SOLDIER_IDS
    )
    no_jobs = len(jobs) == 0

    print("===== BF4PS PHASE 4A FROZEN COHORT VERIFY =====")
    print(f"frozen soldiers: {len(PHASE4A_COHORT)}")
    checks = [
        ("exact frozen soldier/persona/name/platform identities", identity_exact),
        ("all 90 collection_state rows present", all_state_rows),
        ("all 90 detailed states still pristine", all_pristine),
        ("no frozen-cohort jobs exist before seed", no_jobs),
    ]
    for label, ok in checks:
        print(f"{label:<58} {'PASS' if ok else 'FAIL'}")

    if not identity_exact:
        print("identity mismatch detected; refusing Phase 4A start")
    if jobs:
        print("unexpected frozen-cohort jobs:")
        for row in jobs:
            print(
                f"  job={row['job_id']} soldier={row['soldier_id']} "
                f"resource={row['resource']} lane={row['lane']} status={row['status']} "
                f"attempt={row['attempt_count']}"
            )

    print("database writes: 0")
    print("Battlelog requests: 0")
    passed = all(ok for _, ok in checks)
    print(f"PHASE 4A FROZEN COHORT VERIFY: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
