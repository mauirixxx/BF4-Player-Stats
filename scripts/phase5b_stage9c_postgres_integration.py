#!/usr/bin/env python3
"""Destructive-schema integration ONLY on a dedicated empty disposable DB.

Never uses the default BF4PS_DATABASE_URL. Requires explicit isolated URL
and verifies an empty database before running Alembic. No collectors or HTTP.
"""
from __future__ import annotations

import argparse
import os
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from bf4ps.stage9c_supervision import (
    CUTOVER_AT, BOUNDARY_EVENT_ID, SupervisionRefused,
    abort_owned_run, renew_after_inspection, require_guard_lease,
)

REV3 = "0003_request_gates"
REV4 = "0004_stage9c_supervision_runs"
SUFFIX = "_stage9c_integration"


def refuse_unsafe_target(url):
    parsed = make_url(url)
    name = parsed.database or ""
    if parsed.get_backend_name() != "postgresql" or not name.endswith(SUFFIX):
        raise RuntimeError("REFUSING: dedicated PostgreSQL *_stage9c_integration database required")
    if name in ("bf4_playerstats_test", "bf4_playerstats"):
        raise RuntimeError("REFUSING: production database")
    return name


def assert_empty(engine, expected_name):
    with engine.connect() as conn:
        name, recovery, ro = conn.execute(text(
            "SELECT current_database(), pg_is_in_recovery(), current_setting('transaction_read_only')"
        )).one()
        if (name, recovery, ro) != (expected_name, False, "off"):
            raise RuntimeError("REFUSING: wrong database, standby or read-only connection")
        tables = inspect(conn).get_table_names(schema="public")
        if tables:
            raise RuntimeError(f"REFUSING: integration database not empty: {tables}")


def alembic_config(url):
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


def run(url):
    name = refuse_unsafe_target(url)
    engine = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 5})
    previous = os.environ.get("BF4PS_DATABASE_URL")
    try:
        assert_empty(engine, name)
        # migrations/env.py reads BF4PS_DATABASE_URL; force the independently
        # validated explicit URL only within this test process.
        os.environ["BF4PS_DATABASE_URL"] = url
        cfg = alembic_config(url)
        command.upgrade(cfg, REV3)
        with engine.connect() as conn:
            assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == REV3
        command.upgrade(cfg, REV4)
        with engine.begin() as conn:
            assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == REV4
            now = conn.execute(text("SELECT clock_timestamp()")).scalar_one()
            run_id, owner, other = uuid4(), uuid4(), uuid4()
            conn.execute(text("""
                INSERT INTO stage9c_supervision_runs
                (run_id,state,cutover_at,since_event_id,started_at,deadline_at,
                 watchdog_owner,watchdog_generation,heartbeat_at,lease_expires_at)
                VALUES (:run_id,'active',CAST(:cutover AS timestamptz),:boundary,
                        :now,:now + interval '6 hours',:owner,1,:now,
                        :now + interval '20 seconds')
            """), {"run_id": run_id, "cutover": CUTOVER_AT,
                   "boundary": BOUNDARY_EVENT_ID, "now": now, "owner": owner})
            require_guard_lease(conn, run_id)
            for candidate, generation in ((other, 1), (owner, 2)):
                try:
                    renew_after_inspection(conn, run_id=run_id, owner=candidate,
                                           generation=generation, inspection_passed=True)
                except SupervisionRefused:
                    pass
                else:
                    raise AssertionError("fencing failure")
            renew_after_inspection(conn, run_id=run_id, owner=owner,
                                   generation=1, inspection_passed=True)
            abort_owned_run(conn, run_id=run_id, owner=owner,
                            generation=1, reason="integration-test abort")
        with engine.begin() as conn:
            assert conn.execute(text(
                "SELECT state FROM stage9c_supervision_runs WHERE run_id=:id"
            ), {"id": run_id}).scalar_one() == "aborted"
            for operation in (
                lambda: require_guard_lease(conn, run_id),
                lambda: renew_after_inspection(conn, run_id=run_id, owner=owner,
                                               generation=1, inspection_passed=True),
                lambda: abort_owned_run(conn, run_id=run_id, owner=owner,
                                        generation=1, reason="second abort"),
            ):
                try:
                    operation()
                except SupervisionRefused:
                    pass
                else:
                    raise AssertionError("terminal run was accepted")
        # Downgrade only in the dedicated disposable database.
        command.downgrade(cfg, REV3)
        with engine.connect() as conn:
            assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == REV3
            assert "stage9c_supervision_runs" not in inspect(conn).get_table_names()
        command.upgrade(cfg, REV4)
        with engine.connect() as conn:
            assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == REV4
            assert "stage9c_supervision_runs" in inspect(conn).get_table_names()
            assert conn.execute(text("SELECT count(*) FROM stage9c_supervision_runs")).scalar_one() == 0
        print("PASS: isolated PostgreSQL 0003→0004→0003→0004, fenced renewal, sticky abort")
        print("NOTE: disposable database deliberately left at 0004; no production state touched")
    finally:
        if previous is None:
            os.environ.pop("BF4PS_DATABASE_URL", None)
        else:
            os.environ["BF4PS_DATABASE_URL"] = previous
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--isolated-url", required=True, help="Dedicated EMPTY database URL (never production)")
    parser.add_argument("--execute", action="store_true", help="Required to run migrations on isolated DB")
    args = parser.parse_args()
    name = refuse_unsafe_target(args.isolated_url)
    if not args.execute:
        print(f"DRY RUN: would verify EMPTY disposable PostgreSQL database {name!r}")
        return
    run(args.isolated_url)


if __name__ == "__main__":
    main()
