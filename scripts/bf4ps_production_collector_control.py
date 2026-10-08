#!/usr/bin/env python3
"""Fail-closed operator control for production collector drain/resume."""
from __future__ import annotations

import argparse
import socket

from sqlalchemy import create_engine, text

from bf4ps.config import database_url
from bf4ps.production_hosts import HOSTS

EXPECTED_DATABASE = "bf4_playerstats_test"
EXPECTED_REVISION = "0003_request_gates"
STAGE9C_REVISION = "0004_stage9c_supervision_runs"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("drain", "resume"))
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        raise SystemExit("REFUSING: --execute is required")

    host = socket.gethostname().split(".", 1)[0]
    configured = HOSTS.get(host)
    if configured is None:
        raise SystemExit(f"REFUSING: host {host!r} has no production collector identity")

    engine = create_engine(database_url(), pool_pre_ping=True, connect_args={"connect_timeout": 3, "options": "-c statement_timeout=3000 -c lock_timeout=1000"})
    desired = args.action == "drain"
    try:
        with engine.begin() as conn:
            db = conn.execute(text("SELECT current_database()")).scalar_one()
            revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            recovery = bool(conn.execute(text("SELECT pg_is_in_recovery()")).scalar_one())
            read_only = conn.execute(text("SELECT current_setting('transaction_read_only')")).scalar_one()
            allowed_revision = (EXPECTED_REVISION, STAGE9C_REVISION) if desired else (EXPECTED_REVISION,)
            if db != EXPECTED_DATABASE or revision not in allowed_revision or recovery or read_only != "off":
                raise RuntimeError(
                    f"wrong target db={db!r} revision={revision!r} recovery={recovery} read_only={read_only!r}"
                )

            row = conn.execute(text("""
                SELECT collector_uuid,collector_name,hostname,lane,egress_key,
                       enabled,drained,current_job_id,retired_at
                FROM collectors
                WHERE collector_uuid=:uuid
                FOR UPDATE
            """), {"uuid": configured.collector_uuid}).mappings().one_or_none()
            if row is None:
                raise RuntimeError("production collector identity is not registered")
            expected = (
                configured.collector_uuid,
                configured.collector_name,
                host,
                "background",
                configured.egress_key,
            )
            actual = (
                row["collector_uuid"],
                row["collector_name"],
                row["hostname"],
                row["lane"],
                row["egress_key"],
            )
            if actual != expected:
                raise RuntimeError(f"collector identity drift: actual={actual!r} expected={expected!r}")
            if row["retired_at"] is not None:
                raise RuntimeError("collector identity is retired")

            updated = conn.execute(text("""
                UPDATE collectors
                SET drained=:drained, updated_at=now()
                WHERE collector_uuid=:uuid
                  AND retired_at IS NULL
                RETURNING collector_name,hostname,egress_key,enabled,drained,current_job_id
            """), {"uuid": configured.collector_uuid, "drained": desired}).mappings().one()

        print(
            f"BF4PS PRODUCTION COLLECTOR {args.action.upper()}: PASS "
            f"collector={updated['collector_name']} host={updated['hostname']} "
            f"egress={updated['egress_key']} enabled={updated['enabled']} "
            f"drained={updated['drained']} current_job_id={updated['current_job_id']}"
        )
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
