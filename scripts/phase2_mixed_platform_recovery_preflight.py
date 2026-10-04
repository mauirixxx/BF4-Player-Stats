#!/usr/bin/env python3
"""Read-only inspection of retained mixed-platform recovery state."""

from __future__ import annotations
import os
from sqlalchemy import create_engine, text

EXPECTED_REVISION = "0003_request_gates"
COHORT = (17, 18, 19, 93, 94, 95, 105, 106, 107)
EXPECTED_PLATFORMS = {"pc": 3, "ps4": 3, "xboxone": 3}


def main() -> None:
    engine = create_engine(os.environ["BF4PS_DATABASE_URL"])
    with engine.connect() as conn:
        db = conn.execute(text("SELECT current_database()" )).scalar_one()
        recovery = conn.execute(text("SELECT pg_is_in_recovery()" )).scalar_one()
        revision = conn.execute(text("SELECT version_num FROM alembic_version" )).scalar_one()
        db_now = conn.execute(text("SELECT now()" )).scalar_one()
        soldiers = conn.execute(text("""
            SELECT s.soldier_id, s.persona_id, s.platform, s.current_name,
                   cs.detailed_state, cs.detailed_last_attempt_at,
                   cs.detailed_last_success_at, cs.detailed_next_due_at,
                   cs.detailed_consecutive_failures,
                   cs.detailed_last_error_class, cs.detailed_last_error_message,
                   dsc.source_fetched_at
            FROM soldiers AS s
            JOIN collection_state AS cs ON cs.soldier_id = s.soldier_id
            LEFT JOIN detailed_stats_current AS dsc ON dsc.soldier_id = s.soldier_id
            WHERE s.soldier_id = ANY(:cohort)
            ORDER BY s.soldier_id
        """), {"cohort": list(COHORT)}).mappings().all()
        jobs = conn.execute(text("""
            SELECT job_id, soldier_id, status, eligible_at, attempt_count,
                   collector_uuid, lease_token, lease_expires_at,
                   last_error_class, last_error_at,
                   (eligible_at <= now()) AS eligible_now
            FROM collection_jobs
            WHERE soldier_id = ANY(:cohort)
              AND resource = 'detailed'
            ORDER BY job_id
        """), {"cohort": list(COHORT)}).mappings().all()
        outside_jobs = conn.execute(text("""
            SELECT job_id, soldier_id, status, eligible_at,
                   (eligible_at <= now()) AS eligible_now
            FROM collection_jobs
            WHERE resource = 'detailed'
              AND lane = 'background'
              AND NOT (soldier_id = ANY(:cohort))
            ORDER BY job_id
        """), {"cohort": list(COHORT)}).mappings().all()

    print("===== BF4PS PHASE 2 MIXED-PLATFORM RECOVERY PREFLIGHT =====\n")
    print("READ-ONLY RETAINED-STATE INSPECTION")
    print("No feeder pass, queue write, job claim, or Battlelog request is performed.\n")
    print(f"database: {db}\nrecovery: {recovery}\nalembic:  {revision}\ndb now:   {db_now}\ncohort:   {list(COHORT)}")
    if "test" not in db.lower():
        raise SystemExit(f"REFUSING: not a test database: {db}")
    if recovery:
        raise SystemExit("REFUSING: database is in recovery")
    if revision != EXPECTED_REVISION:
        raise SystemExit(f"REFUSING: expected Alembic {EXPECTED_REVISION}, found {revision}")
    if tuple(row["soldier_id"] for row in soldiers) != tuple(sorted(COHORT)):
        raise SystemExit("REFUSING: retained cohort does not match expected soldier IDs")

    print("\n===== RETAINED COHORT STATE =====")
    counts = {platform: 0 for platform in EXPECTED_PLATFORMS}
    never_attempted, successful, other_states = [], [], []
    for row in soldiers:
        counts[row["platform"]] += 1
        state = str(row["detailed_state"])
        if state == "never_attempted": never_attempted.append(int(row["soldier_id"]))
        elif state == "success": successful.append(int(row["soldier_id"]))
        else: other_states.append((int(row["soldier_id"]), state))
        print(f"soldier={row['soldier_id']:<7} {row['platform']:<8} {row['current_name']!r:<24} state={state}")
        print(f"         last_attempt={row['detailed_last_attempt_at']} last_success={row['detailed_last_success_at']}")
        print(f"         next_due={row['detailed_next_due_at']} failures={row['detailed_consecutive_failures']} source_fetched={row['source_fetched_at']}")
        if row["detailed_last_error_class"] or row["detailed_last_error_message"]:
            print(f"         last_error={row['detailed_last_error_class']!r}: {row['detailed_last_error_message']!r}")

    print("\n===== RETAINED COHORT QUEUE =====")
    if jobs:
        for row in jobs:
            print(f"job={row['job_id']:<6} soldier={row['soldier_id']:<7} status={row['status']:<8} attempts={row['attempt_count']:<3} eligible={row['eligible_at']} eligible_now={row['eligible_now']}")
            print(f"         owner={row['collector_uuid']} lease={row['lease_token']} lease_expires={row['lease_expires_at']}")
            print(f"         last_error={row['last_error_class']!r} last_error_at={row['last_error_at']}")
    else:
        print("(empty)")

    print("\n===== OUTSIDE-COHORT DETAILED/BACKGROUND QUEUE =====")
    if outside_jobs:
        for row in outside_jobs:
            print(f"job={row['job_id']:<6} soldier={row['soldier_id']:<7} status={row['status']:<8} eligible={row['eligible_at']} eligible_now={row['eligible_now']}")
    else:
        print("(empty)")

    exact_mix = counts == EXPECTED_PLATFORMS
    expected_shape = len(successful) == 8 and never_attempted == [107] and not other_states
    print("\n===== RETAINED INCIDENT SUMMARY =====")
    print(f"platform counts:     {counts}\nsuccessful soldiers: {successful}\nnever attempted:     {never_attempted}\nother states:        {other_states}\ncohort queue rows:    {len(jobs)}\noutside queue rows:   {len(outside_jobs)}")
    print("\n===== SAFETY / EVIDENCE DECISION =====")
    print("test database:                  PASS\nwritable primary:               PASS\nexpected Alembic head:          PASS")
    print(f"exact 3/3/3 platform cohort:    {'PASS' if exact_mix else 'FAIL'}")
    print(f"retained 8-success/107-pending: {'PASS' if expected_shape else 'CHANGED'}")
    print("external requests:              0\ndatabase writes:                0")
    if not exact_mix:
        raise SystemExit("PREFLIGHT FAIL: platform cohort changed")
    if not expected_shape:
        raise SystemExit("PREFLIGHT STOP: retained incident state differs from expected evidence")
    print("\nPHASE 2 MIXED-PLATFORM RECOVERY PREFLIGHT: PASS")


if __name__ == "__main__":
    main()
