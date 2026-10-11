"""Durable local soak manifest initialization (tcou only, no DB mutations).

The manifest is a coordinator control file, not the authoritative request ledger.
Do not start the soak with this module alone: round reconciliation and workers
remain gated. Exclusive file creation prevents accidentally resetting a run.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path

from sqlalchemy import text

from scripts.stage9c_three_hour_soak_preflight import inspect
from scripts.stage9c_three_site_live_ignition import engine

RUN = "bf4ps-d2-three-hour-soak-20261011-v1"
ROUNDS = 12
ROUND_SECONDS = 900
DURATION_SECONDS = 10800
MAX_ATTEMPTS = 108
DEFAULT_MANIFEST = "/root/bf4ps-d2-tests/three-hour-soak-manifest.json"


def build_manifest():
    if os.uname().nodename != "tcou":
        raise RuntimeError("manifest initialization is restricted to tcou")
    preflight = inspect()
    # Cross-check against a fresh database timestamp to avoid host clock drift.
    with engine().connect() as conn:
        db_time = conn.execute(text("SELECT now()")).scalar_one()
    if db_time.tzinfo is None:
        raise RuntimeError("database time must be timezone-aware")
    now = datetime.now(timezone.utc)
    if abs((now - db_time).total_seconds()) > 5:
        raise RuntimeError("tcou and PostgreSQL clocks differ by more than 5 seconds")
    # The real deadline is assigned only at explicit ignition. No implicit
    # start/deadline is created by a read-only preflight.
    return {
        "schema_version": 1,
        "run_id": RUN,
        "state": "prepared_not_ignited",
        "created_at_utc": now.isoformat(),
        "start_at_utc": None,
        "deadline_at_utc": None,
        "round_seconds": ROUND_SECONDS,
        "duration_seconds": DURATION_SECONDS,
        "rounds_planned": ROUNDS,
        "rounds_enqueued": [],
        "attempt_ceiling": MAX_ATTEMPTS,
        "max_attempts_per_site": 36,
        "request_interval_seconds": 10,
        "http_timeout_seconds": 30,
        "lease_seconds": 120,
        "baseline_event_id": preflight["baseline_event_id"],
        "cohort_soldier_ids": preflight["soldier_ids"],
        "sites": preflight["collectors"],
        "database": preflight["db"],
        "preflight": preflight,
    }


def create_manifest(path: Path, *, execute: bool):
    payload = build_manifest()
    if not execute:
        print(json.dumps(payload, sort_keys=True, indent=2))
        print("DRY RUN: manifest not written")
        return
    if not path.parent.is_dir():
        raise RuntimeError("manifest directory does not exist; create it explicitly")
    # O_EXCL is deliberate. Never overwrite a previous run or resume by guessing.
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "w") as file:
            json.dump(payload, file, sort_keys=True, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        parent_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    except BaseException:
        # Preserve incomplete file for operator inspection; never overwrite it.
        raise
    print(f"MANIFEST CREATED {path} state=prepared_not_ignited")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["init"])
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    create_manifest(Path(args.manifest), execute=args.execute)


if __name__ == "__main__":
    main()
