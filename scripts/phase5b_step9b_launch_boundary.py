#!/usr/bin/env python3
"""Read-only Stage 9B launch boundary capture."""
from __future__ import annotations

from sqlalchemy import create_engine, text

from bf4ps.config import database_url
from bf4ps.production_hosts import HOSTS

EXPECTED_DATABASE = "bf4_playerstats_test"
EXPECTED_REVISION = "0003_request_gates"
CANARY_HOST = "tcou"


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

            row = conn.execute(text("""
                SELECT
                    clock_timestamp() AS cutover_at,
                    COALESCE(MAX(event_id), 0) AS boundary_event_id
                FROM collection_events
            """)).mappings().one()
            background = int(conn.execute(text(
                "SELECT COUNT(*) FROM collection_jobs WHERE lane='background'"
            )).scalar_one())
            owned = int(conn.execute(text(
                "SELECT COUNT(*) FROM collection_jobs WHERE status IN ('claimed','running')"
            )).scalar_one())
            step7 = int(conn.execute(text(
                "SELECT COUNT(*) FROM collection_jobs WHERE reason='phase5b_step7_endurance'"
            )).scalar_one())

            host = HOSTS[CANARY_HOST]
            collector = conn.execute(text("""
                SELECT collector_uuid,collector_name,hostname,lane,egress_key,
                       enabled,drained,current_job_id,retired_at
                FROM collectors
                WHERE collector_uuid=:uuid
            """), {"uuid": host.collector_uuid}).mappings().one_or_none()

        expected = (
            host.collector_uuid,
            host.collector_name,
            CANARY_HOST,
            "background",
            host.egress_key,
        )
        actual = None if collector is None else (
            collector["collector_uuid"],
            collector["collector_name"],
            collector["hostname"],
            collector["lane"],
            collector["egress_key"],
        )
        collector_ok = (
            collector is not None
            and actual == expected
            and collector["enabled"] is True
            and collector["drained"] is False
            and collector["current_job_id"] is None
            and collector["retired_at"] is None
        )
        cutover = row["cutover_at"].isoformat()
        boundary = int(row["boundary_event_id"])

        print("===== BF4PS PHASE 5B STEP 9B LAUNCH BOUNDARY =====")
        print(f"database={db} revision={revision} primary_writable=yes")
        print(f"canary_host={CANARY_HOST} collector_ready={collector_ok}")
        print(f"background_jobs={background} step7_residue={step7} claimed_or_running_jobs={owned}")
        print(f"CUTOVER_AT={cutover}")
        print(f"BOUNDARY_EVENT_ID={boundary}")
        print("external_materialization_process_check=REQUIRED_AFTER_BOUNDARY")
        print("database writes: 0")
        print("Battlelog requests: 0")

        ok = background == 0 and step7 == 0 and owned == 0 and collector_ok
        print("PHASE 5B STEP 9B LAUNCH BOUNDARY: " + ("PASS" if ok else "FAIL"))
        return 0 if ok else 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
