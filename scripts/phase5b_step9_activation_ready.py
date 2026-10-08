#!/usr/bin/env python3
"""Read-only final Stage 9A readiness gate after Step 7 residue cleanup."""
from __future__ import annotations

from sqlalchemy import create_engine, text

from bf4ps.config import database_url
from bf4ps.production_hosts import HOSTS

EXPECTED_DATABASE = "bf4_playerstats_test"
EXPECTED_REVISION = "0003_request_gates"


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

            background = int(conn.execute(text(
                "SELECT COUNT(*) FROM collection_jobs WHERE lane='background'"
            )).scalar_one())
            owned = int(conn.execute(text(
                "SELECT COUNT(*) FROM collection_jobs WHERE status IN ('claimed','running')"
            )).scalar_one())
            step7 = int(conn.execute(text(
                "SELECT COUNT(*) FROM collection_jobs WHERE reason='phase5b_step7_endurance'"
            )).scalar_one())

            rows = conn.execute(text("""
                SELECT collector_uuid,collector_name,hostname,lane,egress_key,
                       enabled,drained,current_job_id,retired_at
                FROM collectors
                WHERE collector_uuid=ANY(:uuids)
                ORDER BY hostname
            """), {"uuids": [h.collector_uuid for h in HOSTS.values()]}).mappings().all()

        expected = {
            (
                h.collector_uuid,
                h.collector_name,
                host,
                "background",
                h.egress_key,
            )
            for host, h in HOSTS.items()
        }
        actual = {
            (
                r["collector_uuid"],
                r["collector_name"],
                r["hostname"],
                r["lane"],
                r["egress_key"],
            )
            for r in rows
        }
        retired = sum(r["retired_at"] is not None for r in rows)
        current_jobs = sum(r["current_job_id"] is not None for r in rows)

        print("===== BF4PS PHASE 5B STEP 9 FINAL ACTIVATION READINESS =====")
        print(f"database={db} revision={revision} primary_writable=yes")
        print(
            f"background_jobs={background} step7_residue={step7} "
            f"claimed_or_running_jobs={owned}"
        )
        print(
            f"production_collectors={len(rows)} retired={retired} "
            f"collectors_with_current_job={current_jobs}"
        )
        for row in rows:
            print(
                f"  COLLECTOR host={row['hostname']} name={row['collector_name']} "
                f"egress={row['egress_key']} enabled={row['enabled']} drained={row['drained']}"
            )
        print("external_materialization_process_check=REQUIRED")
        print("database writes: 0")
        print("Battlelog requests: 0")

        ok = (
            background == 0
            and step7 == 0
            and owned == 0
            and len(rows) == len(HOSTS)
            and actual == expected
            and retired == 0
            and current_jobs == 0
        )
        print("PHASE 5B STEP 9 FINAL ACTIVATION READINESS: " + ("PASS" if ok else "FAIL"))
        return 0 if ok else 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
