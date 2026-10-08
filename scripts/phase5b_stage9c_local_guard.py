#!/usr/bin/env python3
"""Stage 9C host-local systemd guard; dry-run unless explicitly armed.

This guard must be run under a separate transient systemd unit with
BindsTo=/PartOf= relationships managed by the launcher. It never makes
Battlelog requests or modifies PostgreSQL.
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import socket
import subprocess
import time
from uuid import UUID

from sqlalchemy import create_engine, text

from bf4ps.config import database_url
from bf4ps.production_hosts import HOSTS
from bf4ps.stage9c_supervision import REVISION, require_guard_lease

LOG = logging.getLogger("bf4ps.stage9c.local_guard")
STOP = False
EXPECTED_DB = "bf4_playerstats_test"
EXPECTED_REV = REVISION
COLLECTOR_UNIT = "bf4ps-stage9c-collector.service"
MATERIALIZER_UNIT = "bf4ps-stage9c-materializer.service"


def request_stop(*_args):
    global STOP
    STOP = True


def validate_unit_name(unit):
    if unit not in (COLLECTOR_UNIT, MATERIALIZER_UNIT):
        raise ValueError(f"refusing unknown unit {unit!r}")


def stop_units(host, *, armed, runner=subprocess.run):
    units = [COLLECTOR_UNIT]
    if host == "tcou":
        units.append(MATERIALIZER_UNIT)
    for unit in units:
        validate_unit_name(unit)
        if armed:
            LOG.critical("STOPPING %s", unit)
            runner(["systemctl", "stop", "--no-block", unit], check=True, timeout=10)
        else:
            LOG.warning("DRY RUN: would stop %s", unit)


def check_db(conn, host, run_id):
    db = conn.execute(text("SELECT current_database()")).scalar_one()
    rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    recovery = conn.execute(text("SELECT pg_is_in_recovery()")).scalar_one()
    readonly = conn.execute(text("SELECT current_setting('transaction_read_only')")).scalar_one()
    if (db, rev, recovery, readonly) != (EXPECTED_DB, EXPECTED_REV, False, "off"):
        raise RuntimeError(f"database safety mismatch db={db} revision={rev} recovery={recovery} read_only={readonly}")
    identity = HOSTS[host]
    row = conn.execute(text("""
        SELECT collector_name, hostname, egress_key, lane, enabled, drained, retired_at
        FROM collectors WHERE collector_uuid=:uuid
    """), {"uuid": identity.collector_uuid}).mappings().one_or_none()
    if row is None:
        raise RuntimeError("collector registry identity missing")
    if (row["collector_name"], row["hostname"], row["egress_key"], row["lane"], row["retired_at"]) != (
        identity.collector_name, host, identity.egress_key, "background", None
    ):
        raise RuntimeError("collector identity drift")
    if not row["enabled"] or row["drained"]:
        raise RuntimeError("collector disabled or drained")
    require_guard_lease(conn, run_id)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True, type=UUID, help="Exact explicitly authorized Stage 9C run UUID")
    parser.add_argument("--armed", action="store_true", help="Permit local systemctl stop")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval-seconds", type=int, default=5)
    args = parser.parse_args()
    if args.interval_seconds < 1 or args.interval_seconds > 5:
        parser.error("interval must be between 1 and 5 seconds")
    host = socket.gethostname().split(".", 1)[0]
    if host not in HOSTS:
        parser.error(f"unsupported hostname {host}")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    engine = create_engine(database_url(), pool_pre_ping=True, connect_args={"connect_timeout": 3, "options": "-c statement_timeout=3000 -c lock_timeout=1000 -c idle_in_transaction_session_timeout=5000"})
    try:
        while not STOP:
            try:
                with engine.connect() as conn:
                    check_db(conn, host, args.run_id)
            except Exception:
                LOG.exception("LOCAL SAFETY FAILURE")
                try:
                    stop_units(host, armed=args.armed)
                except Exception:
                    LOG.exception("FAILED TO STOP LOCAL UNITS; supervisor must kill collector")
                return 2
            LOG.info("LOCAL GUARD PASS host=%s armed=%s", host, args.armed)
            if args.once:
                return 0
            time.sleep(args.interval_seconds)
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
