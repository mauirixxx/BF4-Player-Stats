#!/usr/bin/env python3
"""Read-only verification of the Phase 5B Step 9 Step-7-residue cleanup."""
from __future__ import annotations

from collections import Counter

from sqlalchemy import create_engine, text

from bf4ps.config import database_url
from bf4ps.production_hosts import COLLECTOR_UUIDS, RESOURCES

EXPECTED_DATABASE = "bf4_playerstats_test"
EXPECTED_REVISION = "0003_request_gates"
RUN_MARKER_EVENT_TYPE = "phase5b_step7_run_started"
LIVE_START_EVENT_TYPE = "phase5b_step7_live_started"
RUN_NUMBER = "1"
EXPECTED_ATTEMPTS = 3888
EXPECTED_UNIQUE_JOBS = 3864
EXPECTED_RETRIES = 24
EXPECTED_SUCCESSES = 3864
EXPECTED_FAILURES = 24
EXPECTED_DISPLACED_WEAPON_STATES = 24


def main() -> int:
    engine = create_engine(database_url(), pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            db = conn.execute(text("SELECT current_database()")).scalar_one()
            revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            recovery = bool(conn.execute(text("SELECT pg_is_in_recovery()")).scalar_one())
            read_only = conn.execute(text("SELECT current_setting('transaction_read_only')")).scalar_one()
            if db != EXPECTED_DATABASE or revision != EXPECTED_REVISION or recovery or read_only != "off":
                raise RuntimeError(
                    f"wrong target db={db!r} revision={revision!r} recovery={recovery} read_only={read_only!r}"
                )

            markers = conn.execute(text("""
                SELECT event_id,metadata FROM collection_events
                WHERE event_type=:t AND metadata->>'run_number'=:n ORDER BY event_id
            """), {"t": RUN_MARKER_EVENT_TYPE, "n": RUN_NUMBER}).mappings().all()
            lives = conn.execute(text("""
                SELECT event_id,occurred_at FROM collection_events
                WHERE event_type=:t AND metadata->>'run_number'=:n ORDER BY event_id
            """), {"t": LIVE_START_EVENT_TYPE, "n": RUN_NUMBER}).mappings().all()
            if len(markers) != 1 or len(lives) != 1:
                raise RuntimeError(f"accepted Step 7 markers changed run={len(markers)} live={len(lives)}")

            boundary = int(markers[0]["event_id"])
            ids = [int(x) for x in markers[0]["metadata"]["cohort_soldier_ids"]]
            if len(ids) != 1296 or len(set(ids)) != 1296:
                raise RuntimeError("Step 7 cohort marker changed")

            params = {"b": boundary, "ids": ids, "resources": list(RESOURCES)}
            attempts = conn.execute(text("""
                SELECT job_id,attempt_number,resource,platform,collector_uuid
                FROM collection_events
                WHERE event_id>:b AND soldier_id=ANY(:ids) AND resource=ANY(:resources)
                  AND lane='background' AND event_type='collection_attempt_started'
            """), params).mappings().all()
            terminals = conn.execute(text("""
                SELECT job_id,attempt_number,event_type
                FROM collection_events
                WHERE event_id>:b AND soldier_id=ANY(:ids) AND resource=ANY(:resources)
                  AND lane='background' AND event_type IN ('collection_success','collection_failure')
            """), params).mappings().all()

            remaining_step7 = int(conn.execute(text("""
                SELECT COUNT(*) FROM collection_jobs
                WHERE soldier_id=ANY(:ids) AND reason='phase5b_step7_endurance'
            """), {"ids": ids}).scalar_one())
            unexpected_background = int(conn.execute(text("""
                SELECT COUNT(*) FROM collection_jobs WHERE lane='background'
            """)).scalar_one())

            displaced = conn.execute(text("""
                SELECT soldier_id
                FROM collection_state
                WHERE soldier_id=ANY(:ids)
                  AND weapons_state='never_attempted'
                  AND weapons_last_attempt_at IS NULL
                  AND weapons_last_success_at IS NULL
                  AND weapons_next_due_at IS NULL
                  AND weapons_consecutive_failures=0
                  AND weapons_last_error_class IS NULL
                  AND weapons_last_error_message IS NULL
                ORDER BY soldier_id
            """), {"ids": ids}).scalars().all()

            owned = int(conn.execute(text("""
                SELECT COUNT(*) FROM collection_jobs
                WHERE status IN ('claimed','running')
                  AND collector_uuid=ANY(:uuids)
            """), {"uuids": list(COLLECTOR_UUIDS)}).scalar_one())

        akeys = [(int(r["job_id"]), int(r["attempt_number"])) for r in attempts]
        tkeys = [(int(r["job_id"]), int(r["attempt_number"])) for r in terminals]
        ac = Counter(akeys)
        tc = Counter(tkeys)
        unique_jobs = len({int(r["job_id"]) for r in attempts})
        retries = len(attempts) - unique_jobs
        successes = sum(r["event_type"] == "collection_success" for r in terminals)
        failures = sum(r["event_type"] == "collection_failure" for r in terminals)
        foreign = sum(r["collector_uuid"] not in COLLECTOR_UUIDS for r in attempts)
        duplicate_attempts = sum(v - 1 for v in ac.values() if v > 1)
        duplicate_terminals = sum(v - 1 for v in tc.values() if v > 1)
        missing_terminals = len(set(ac) - set(tc))
        orphan_terminals = len(set(tc) - set(ac))

        print("===== BF4PS PHASE 5B STEP 9 POST-CLEANUP VERIFICATION =====")
        print(f"database={db} revision={revision} primary_writable=yes")
        print(f"run_marker_event_id={boundary} live_start_event_id={lives[0]['event_id']}")
        print(
            f"physical_attempts={len(attempts)} unique_jobs_attempted={unique_jobs} "
            f"retry_attempts={retries}"
        )
        print(f"terminal_events={len(terminals)} success={successes} failure={failures}")
        print(
            f"duplicate_attempt_keys={duplicate_attempts} duplicate_terminal_keys={duplicate_terminals} "
            f"attempts_without_terminal={missing_terminals} terminals_without_start={orphan_terminals}"
        )
        print(
            f"step7_queue_residue={remaining_step7} all_background_jobs={unexpected_background} "
            f"claimed_or_running_by_production_collectors={owned}"
        )
        print(
            f"preserved_displaced_pristine_weapon_states={len(displaced)} "
            f"expected={EXPECTED_DISPLACED_WEAPON_STATES}"
        )
        print(f"foreign_step7_physical_starts={foreign}")
        print("database writes: 0")
        print("Battlelog requests: 0")

        ok = (
            len(attempts) == EXPECTED_ATTEMPTS
            and unique_jobs == EXPECTED_UNIQUE_JOBS
            and retries == EXPECTED_RETRIES
            and len(terminals) == EXPECTED_ATTEMPTS
            and successes == EXPECTED_SUCCESSES
            and failures == EXPECTED_FAILURES
            and duplicate_attempts == 0
            and duplicate_terminals == 0
            and missing_terminals == 0
            and orphan_terminals == 0
            and remaining_step7 == 0
            and unexpected_background == 0
            and owned == 0
            and len(displaced) == EXPECTED_DISPLACED_WEAPON_STATES
            and foreign == 0
        )
        print("PHASE 5B STEP 9 POST-CLEANUP VERIFICATION: " + ("PASS" if ok else "FAIL"))
        return 0 if ok else 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
