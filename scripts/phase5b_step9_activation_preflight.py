#!/usr/bin/env python3
"""Read-only Phase 5B Step 9 production activation preflight."""
from __future__ import annotations

from sqlalchemy import create_engine, text

from bf4ps.config import database_url
from bf4ps.production_hosts import HOSTS

EXPECTED_DATABASE = "bf4_playerstats_test"
EXPECTED_REVISION = "0003_request_gates"
EXPECTED_RESIDUE = 24
RUN_MARKER_EVENT_TYPE = "phase5b_step7_run_started"
LIVE_START_EVENT_TYPE = "phase5b_step7_live_started"
RUN_NUMBER = "1"


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
                SELECT event_id, metadata FROM collection_events
                WHERE event_type=:t AND metadata->>'run_number'=:n ORDER BY event_id
            """), {"t": RUN_MARKER_EVENT_TYPE, "n": RUN_NUMBER}).mappings().all()
            live = conn.execute(text("""
                SELECT event_id, occurred_at FROM collection_events
                WHERE event_type=:t AND metadata->>'run_number'=:n ORDER BY event_id
            """), {"t": LIVE_START_EVENT_TYPE, "n": RUN_NUMBER}).mappings().all()
            if len(markers) != 1 or len(live) != 1:
                raise RuntimeError(
                    f"accepted Step 7 evidence missing/ambiguous markers={len(markers)} live_starts={len(live)}"
                )
            ids = [int(x) for x in markers[0]["metadata"]["cohort_soldier_ids"]]
            if len(ids) != 1296 or len(set(ids)) != 1296:
                raise RuntimeError("Step 7 marker cohort is not the accepted 1296 unique soldiers")

            residue = conn.execute(text("""
                SELECT j.job_id, j.soldier_id
                FROM collection_jobs AS j
                JOIN collection_state AS cs ON cs.soldier_id=j.soldier_id
                WHERE j.soldier_id=ANY(:ids)
                  AND j.resource='weapons'
                  AND j.lane='background'
                  AND j.priority_class='bootstrap'
                  AND j.reason='phase5b_step7_endurance'
                  AND j.status='pending'
                  AND j.attempt_count=0
                  AND j.collector_uuid IS NULL
                  AND j.lease_token IS NULL
                  AND j.claimed_at IS NULL
                  AND j.started_at IS NULL
                  AND j.lease_expires_at IS NULL
                  AND j.last_error_class IS NULL
                  AND j.last_error_at IS NULL
                  AND cs.weapons_state='never_attempted'
                  AND cs.weapons_consecutive_failures=0
                ORDER BY j.job_id
            """), {"ids": ids}).mappings().all()
            all_step7 = int(conn.execute(text("""
                SELECT COUNT(*) FROM collection_jobs
                WHERE soldier_id=ANY(:ids) AND reason='phase5b_step7_endurance'
            """), {"ids": ids}).scalar_one())
            if len(residue) != EXPECTED_RESIDUE or all_step7 != EXPECTED_RESIDUE:
                raise RuntimeError(
                    f"Step 7 residue mismatch pristine={len(residue)} total={all_step7} expected={EXPECTED_RESIDUE}"
                )

            unexpected_background = int(conn.execute(text("""
                SELECT COUNT(*) FROM collection_jobs
                WHERE lane='background' AND reason<>'phase5b_step7_endurance'
            """)).scalar_one())
            if unexpected_background:
                raise RuntimeError(
                    f"unexpected non-Step7 background queue exists: {unexpected_background}"
                )

            expected = {
                h.collector_uuid: (h.collector_name, hostname, h.egress_key)
                for hostname, h in HOSTS.items()
            }
            rows = conn.execute(text("""
                SELECT collector_uuid,collector_name,hostname,egress_key,enabled,drained,
                       heartbeat_state,current_job_id,retired_at
                FROM collectors
                WHERE collector_uuid=ANY(:uuids)
                ORDER BY collector_name
            """), {"uuids": list(expected)}).mappings().all()
            if len(rows) != len(expected):
                raise RuntimeError(f"expected {len(expected)} production collectors; found {len(rows)}")
            for row in rows:
                configured = expected[row["collector_uuid"]]
                actual = (row["collector_name"], row["hostname"], row["egress_key"])
                if actual != configured or row["retired_at"] is not None:
                    raise RuntimeError(
                        f"collector identity mismatch uuid={row['collector_uuid']} actual={actual} expected={configured}"
                    )
                if row["current_job_id"] is not None:
                    raise RuntimeError(
                        f"collector {row['collector_name']} still owns current_job_id={row['current_job_id']}"
                    )

            claimed_running = int(conn.execute(text("""
                SELECT COUNT(*) FROM collection_jobs
                WHERE status IN ('claimed','running')
                  AND collector_uuid=ANY(:uuids)
            """), {"uuids": list(expected)}).scalar_one())
            if claimed_running:
                raise RuntimeError(f"production collectors still own claimed/running jobs: {claimed_running}")

        print("===== BF4PS PHASE 5B STEP 9 ACTIVATION PREFLIGHT =====")
        print(
            f"database={db} revision={revision} primary_writable=yes "
            f"run_marker_event_id={markers[0]['event_id']} live_start_event_id={live[0]['event_id']}"
        )
        print(f"step7_residue={len(residue)} pristine_pending_weapons expected={EXPECTED_RESIDUE}")
        print("unexpected_non_step7_background_jobs=0 claimed_or_running_by_production_collectors=0")
        print("collectors=hnl-01,kah-01,tcou identity/ownership: PASS")
        print("database writes: 0")
        print("Battlelog requests: 0")
        print("PHASE 5B STEP 9 ACTIVATION PREFLIGHT: PASS")
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
