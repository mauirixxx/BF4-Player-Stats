#!/usr/bin/env python3
"""Stage 9C database safety watchdog. No Battlelog requests.

Runs in read-only mode by default. --armed permits a transactionally
validated fleet-wide drain when an abort condition is confirmed.
A drain stops new claims, not in-flight HTTP or OS processes.
"""
from __future__ import annotations

import argparse
import logging
import signal
import time
from uuid import UUID
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, text

from bf4ps.config import database_url
from bf4ps.production_hosts import HOSTS, RESOURCES
from bf4ps.stage9c_supervision import (
    REVISION, CUTOVER_AT, BOUNDARY_EVENT_ID, abort_owned_run,
    renew_after_inspection, require_guard_lease,
)

LOG = logging.getLogger("bf4ps.stage9c.watchdog")
STOP = False
EXPECTED_DB = "bf4_playerstats_test"
EXPECTED_REV = REVISION
CEILING = 1296
IDENTITIES = {host.collector_uuid: (host.collector_name, name, host.egress_key)
              for name, host in HOSTS.items()}


def request_stop(*_args):
    global STOP
    STOP = True


def validate_target(conn):
    db = conn.execute(text("SELECT current_database()")).scalar_one()
    rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    recovery = conn.execute(text("SELECT pg_is_in_recovery()")).scalar_one()
    read_only = conn.execute(text("SELECT current_setting('transaction_read_only')")).scalar_one()
    if (db, rev, recovery, read_only) != (EXPECTED_DB, EXPECTED_REV, False, "off"):
        raise RuntimeError(f"unsafe target: db={db} revision={rev} recovery={recovery} read_only={read_only}")


def inspect(conn, *, boundary: int, cutover: datetime, grace_seconds: int):
    validate_target(conn)
    now = conn.execute(text("SELECT now()")).scalar_one()
    events = conn.execute(text("""
        SELECT event_id, occurred_at, event_type, collector_uuid, job_id,
               attempt_number, http_status, error_class, lane, resource
        FROM collection_events
        WHERE event_id > :boundary
        ORDER BY event_id
    """), {"boundary": boundary}).mappings().all()
    starts = {}
    terminals = {}
    issues = []
    for e in events:
        if e["event_type"] == "collection_persistence_failure" or e["http_status"] in (403, 429) or e["error_class"] == "battlelog_throttle":
            issues.append(f"abort event_id={e['event_id']} type={e['event_type']} http={e['http_status']} class={e['error_class']}")
        if e["lane"] != "background" or e["resource"] not in RESOURCES:
            continue
        key = (e["job_id"], e["attempt_number"])
        if e["event_type"] == "collection_attempt_started":
            if key in starts:
                issues.append(f"duplicate start {key}")
            starts[key] = e
            if e["collector_uuid"] not in IDENTITIES:
                issues.append(f"foreign collector event_id={e['event_id']}")
        elif e["event_type"] in ("collection_success", "collection_failure"):
            if key in terminals:
                issues.append(f"duplicate terminal {key}")
            terminals[key] = e
    for key in terminals.keys() - starts.keys():
        issues.append(f"terminal without start {key}")
    for key in starts.keys() - terminals.keys():
        if now - starts[key]["occurred_at"] > timedelta(seconds=grace_seconds):
            issues.append(f"unclosed physical attempt {key}")
    times = sorted(e["occurred_at"] for e in starts.values())
    left = 0
    maximum = 0
    for right, stamp in enumerate(times):
        while left <= right and times[left] <= stamp - timedelta(hours=1):
            left += 1
        maximum = max(maximum, right - left + 1)
    if maximum > CEILING:
        issues.append(f"rolling budget exceeded {maximum}>{CEILING}")
    bad = conn.execute(text("""
        SELECT COUNT(*) FROM collection_jobs
        WHERE lane='background' AND resource=ANY(:resources)
          AND (reason NOT IN ('bf4sw_new_soldier','bf4sw_active_refresh')
               OR eligible_at < :cutover)
    """), {"resources": list(RESOURCES), "cutover": cutover}).scalar_one()
    if bad:
        issues.append(f"invalid background queue provenance count={bad}")
    rows = conn.execute(text("""
        SELECT collector_uuid,collector_name,hostname,egress_key,lane,retired_at
        FROM collectors WHERE collector_uuid=ANY(:uuids)
    """), {"uuids": list(IDENTITIES)}).mappings().all()
    if len(rows) != len(IDENTITIES):
        issues.append(f"collector registry incomplete count={len(rows)}")
    for row in rows:
        if (row["collector_name"],row["hostname"],row["egress_key"]) != IDENTITIES[row["collector_uuid"]] or row["lane"] != "background" or row["retired_at"] is not None:
            issues.append(f"collector identity drift uuid={row['collector_uuid']}")
    return issues, len(starts), len(terminals), maximum


def drain_fleet(conn):
    """Validate identities and drain all three within caller transaction."""
    validate_target(conn)
    rows = conn.execute(text("""
        SELECT collector_uuid,collector_name,hostname,egress_key,lane,retired_at
        FROM collectors WHERE collector_uuid=ANY(:uuids) FOR UPDATE
    """), {"uuids": list(IDENTITIES)}).mappings().all()
    if len(rows) != len(IDENTITIES):
        raise RuntimeError("cannot drain: missing registered collector")
    for r in rows:
        if (r["collector_name"],r["hostname"],r["egress_key"]) != IDENTITIES[r["collector_uuid"]] or r["lane"] != "background" or r["retired_at"] is not None:
            raise RuntimeError("cannot drain: identity drift")
    count = conn.execute(text("""
        UPDATE collectors SET drained=true,updated_at=now()
        WHERE collector_uuid=ANY(:uuids) AND retired_at IS NULL
    """), {"uuids": list(IDENTITIES)}).rowcount
    if count != len(IDENTITIES):
        raise RuntimeError("fleet drain incomplete")
    return count


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True, type=UUID)
    parser.add_argument("--watchdog-owner", required=True, type=UUID)
    parser.add_argument("--watchdog-generation", required=True, type=int)
    parser.add_argument("--cutover-at", required=True)
    parser.add_argument("--since-event-id", required=True, type=int)
    parser.add_argument("--interval-seconds", type=int, default=5)
    parser.add_argument("--inflight-grace-seconds", type=int, default=150)
    parser.add_argument("--armed", action="store_true", help="Allow atomic drain on abort")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    cutover = datetime.fromisoformat(args.cutover_at)
    if (cutover.tzinfo is None or cutover.utcoffset() is None
            or cutover != datetime.fromisoformat(CUTOVER_AT)
            or args.since_event_id != BOUNDARY_EVENT_ID
            or args.watchdog_generation < 1
            or args.interval_seconds < 1 or args.interval_seconds > 5
            or args.inflight_grace_seconds < 60):
        parser.error("invalid cutover/boundary/interval/grace")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    engine = create_engine(database_url(), pool_pre_ping=True, connect_args={"connect_timeout": 3, "options": "-c statement_timeout=3000 -c lock_timeout=1000 -c idle_in_transaction_session_timeout=5000"})
    try:
        while not STOP:
            try:
                # The independent inspection and fenced renewal share one
                # transaction. A failed inspection never extends the lease.
                with engine.begin() as conn:
                    validate_target(conn)
                    require_guard_lease(conn, args.run_id)
                    issues, starts, terminals, maximum = inspect(
                        conn, boundary=args.since_event_id, cutover=cutover,
                        grace_seconds=args.inflight_grace_seconds,
                    )
                    if issues:
                        LOG.critical("ABORT: %s", "; ".join(issues))
                        if args.armed:
                            abort_owned_run(
                                conn, run_id=args.run_id,
                                owner=args.watchdog_owner,
                                generation=args.watchdog_generation,
                                reason="; ".join(issues)[:4000],
                            )
                            drained = drain_fleet(conn)
                            LOG.critical("ABORT + FLEET DRAIN: %d collectors", drained)
                        else:
                            LOG.warning("DRY RUN: no abort or drain performed")
                    elif args.armed:
                        renew_after_inspection(
                            conn, run_id=args.run_id,
                            owner=args.watchdog_owner,
                            generation=args.watchdog_generation,
                            inspection_passed=True,
                        )
                if issues:
                    return 2
                LOG.info("PASS starts=%d terminals=%d rolling_max=%d armed=%s",
                         starts, terminals, maximum, args.armed)
            except Exception:
                LOG.exception("WATCHDOG UNHEALTHY: cannot verify safety")
                # No blind renewal or drain: an uncertain transaction must
                # fail closed through independent guard lease expiry.
                return 3
            if args.once:
                return 0
            time.sleep(args.interval_seconds)
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
