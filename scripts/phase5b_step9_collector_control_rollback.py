#!/usr/bin/env python3
"""Rollback-only live DB exercise for production collector drain/resume."""
from __future__ import annotations

import socket

from sqlalchemy import create_engine, text

from bf4ps.config import database_url
from bf4ps.production_hosts import HOSTS

EXPECTED_DATABASE = "bf4_playerstats_test"
EXPECTED_REVISION = "0003_request_gates"


def _read(conn, uuid):
    return conn.execute(text("""
        SELECT collector_uuid,collector_name,hostname,lane,egress_key,
               enabled,drained,current_job_id,retired_at
        FROM collectors
        WHERE collector_uuid=:uuid
    """), {"uuid": uuid}).mappings().one_or_none()


def main() -> int:
    host = socket.gethostname().split(".", 1)[0]
    configured = HOSTS.get(host)
    if configured is None:
        raise SystemExit(f"REFUSING: host {host!r} has no production collector identity")

    engine = create_engine(database_url(), pool_pre_ping=True)
    try:
        conn = engine.connect()
        tx = conn.begin()
        try:
            db = conn.execute(text("SELECT current_database()")).scalar_one()
            revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            recovery = bool(conn.execute(text("SELECT pg_is_in_recovery()")).scalar_one())
            read_only = conn.execute(text("SELECT current_setting('transaction_read_only')")).scalar_one()
            if db != EXPECTED_DATABASE or revision != EXPECTED_REVISION or recovery or read_only != "off":
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
            if actual != expected or row["retired_at"] is not None:
                raise RuntimeError(f"collector identity mismatch or retired: actual={actual!r}")

            original = bool(row["drained"])
            toggled = not original
            inside = conn.execute(text("""
                UPDATE collectors
                SET drained=:drained, updated_at=now()
                WHERE collector_uuid=:uuid AND retired_at IS NULL
                RETURNING drained
            """), {"uuid": configured.collector_uuid, "drained": toggled}).scalar_one()
            if bool(inside) != toggled:
                raise RuntimeError("rollback exercise did not observe toggled drained value")
        finally:
            tx.rollback()
            conn.close()

        with engine.connect() as verify:
            after = _read(verify, configured.collector_uuid)
            if after is None:
                raise RuntimeError("collector disappeared after rollback")
            if bool(after["drained"]) != original:
                raise RuntimeError(
                    f"ROLLBACK FAILURE: drained persisted as {after['drained']!r}; expected {original!r}"
                )

        print("===== BF4PS PRODUCTION COLLECTOR CONTROL ROLLBACK EXERCISE =====")
        print(f"database={db} revision={revision} primary_writable=yes")
        print(
            f"collector={configured.collector_name} host={host} egress={configured.egress_key} "
            f"original_drained={original} transaction_observed_drained={toggled} "
            f"post_rollback_drained={bool(after['drained'])}"
        )
        print("persistent database changes: 0")
        print("Battlelog requests: 0")
        print("PRODUCTION COLLECTOR CONTROL ROLLBACK EXERCISE: PASS")
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
