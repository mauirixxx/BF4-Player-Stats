#!/usr/bin/env python3
"""Fail-closed cleanup of the accepted Phase 5B Step 7 residual queue rows."""
from __future__ import annotations

import argparse

from sqlalchemy import create_engine, text

from bf4ps.config import database_url

EXPECTED_DATABASE = "bf4_playerstats_test"
EXPECTED_REVISION = "0003_request_gates"
EXPECTED_COUNT = 24
RUN_MARKER_EVENT_TYPE = "phase5b_step7_run_started"
RUN_NUMBER = "1"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Required to commit deletion of the exact accepted Step 7 residue.",
    )
    args = parser.parse_args()
    if not args.execute:
        raise SystemExit("REFUSING: pass --execute after a successful Step 9 preflight")

    engine = create_engine(database_url(), pool_pre_ping=True)
    try:
        with engine.begin() as conn:
            conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('bf4ps:phase5b-step9-residue-cleanup'))"))
            db = conn.execute(text("SELECT current_database()")).scalar_one()
            revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            recovery = bool(conn.execute(text("SELECT pg_is_in_recovery()")).scalar_one())
            read_only = conn.execute(text("SELECT current_setting('transaction_read_only')")).scalar_one()
            if db != EXPECTED_DATABASE or revision != EXPECTED_REVISION or recovery or read_only != "off":
                raise RuntimeError(
                    f"wrong target db={db!r} revision={revision!r} recovery={recovery} read_only={read_only!r}"
                )

            markers = conn.execute(
                text(
                    """
                    SELECT event_id, metadata
                    FROM collection_events
                    WHERE event_type = :event_type
                      AND metadata->>'run_number' = :run_number
                    ORDER BY event_id
                    """
                ),
                {"event_type": RUN_MARKER_EVENT_TYPE, "run_number": RUN_NUMBER},
            ).mappings().all()
            if len(markers) != 1:
                raise RuntimeError(f"expected exactly one Step 7 run marker; found {len(markers)}")
            ids = [int(x) for x in markers[0]["metadata"]["cohort_soldier_ids"]]
            if len(ids) != 1296 or len(set(ids)) != 1296:
                raise RuntimeError("Step 7 marker cohort is not the accepted 1296 unique soldiers")

            rows = conn.execute(
                text(
                    """
                    SELECT j.job_id, j.soldier_id
                    FROM collection_jobs AS j
                    JOIN collection_state AS cs ON cs.soldier_id = j.soldier_id
                    WHERE j.soldier_id = ANY(:ids)
                      AND j.resource = 'weapons'
                      AND j.lane = 'background'
                      AND j.priority_class = 'bootstrap'
                      AND j.reason = 'phase5b_step7_endurance'
                      AND j.status = 'pending'
                      AND j.attempt_count = 0
                      AND j.collector_uuid IS NULL
                      AND j.lease_token IS NULL
                      AND j.claimed_at IS NULL
                      AND j.started_at IS NULL
                      AND j.lease_expires_at IS NULL
                      AND j.last_error_class IS NULL
                      AND j.last_error_at IS NULL
                      AND cs.weapons_state = 'never_attempted'
                      AND cs.weapons_consecutive_failures = 0
                    ORDER BY j.job_id
                    FOR UPDATE OF j, cs
                    """
                ),
                {"ids": ids},
            ).mappings().all()
            if len(rows) != EXPECTED_COUNT:
                raise RuntimeError(
                    f"accepted Step 7 residue shape changed: expected {EXPECTED_COUNT}, found {len(rows)}"
                )

            all_step7_jobs = int(
                conn.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM collection_jobs
                        WHERE soldier_id = ANY(:ids)
                          AND reason = 'phase5b_step7_endurance'
                        """
                    ),
                    {"ids": ids},
                ).scalar_one()
            )
            if all_step7_jobs != EXPECTED_COUNT:
                raise RuntimeError(
                    f"unexpected Step 7 queue residue exists: expected total {EXPECTED_COUNT}, found {all_step7_jobs}"
                )

            job_ids = [int(row["job_id"]) for row in rows]
            deleted = conn.execute(
                text("DELETE FROM collection_jobs WHERE job_id = ANY(:job_ids)"),
                {"job_ids": job_ids},
            )
            if int(deleted.rowcount or 0) != EXPECTED_COUNT:
                raise RuntimeError(
                    f"cleanup delete count mismatch: expected {EXPECTED_COUNT}, deleted {deleted.rowcount}"
                )

            remaining = int(
                conn.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM collection_jobs
                        WHERE soldier_id = ANY(:ids)
                          AND reason = 'phase5b_step7_endurance'
                        """
                    ),
                    {"ids": ids},
                ).scalar_one()
            )
            if remaining != 0:
                raise RuntimeError(f"Step 7 residue remains after cleanup: {remaining}")

        print("BF4PS PHASE 5B STEP 9 RESIDUE CLEANUP: PASS")
        print(f"deleted_jobs={EXPECTED_COUNT} collection_events_deleted=0 collection_state_rows_rewritten=0")
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
