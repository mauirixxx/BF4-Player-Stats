"""Bounded synthetic D2 claim/release soak worker; absolutely no HTTP.

Runs one worker identity. The coordinator provisions/cleans the cohort separately.
Use only against dedicated scratch D2 with --execute and a verified manifest/state.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import time
from pathlib import Path

from sqlalchemy import create_engine

from bf4ps.collection_jobs import claim_next_job, mark_job_running, release_for_retry
from scripts.phase5b_three_site_claim_worker import validate_claim_cohort
from scripts.phase5b_three_site_d2_coordinator import validate_state
from scripts.phase5b_three_site_manifest import validate_manifest_document
from scripts.phase5b_three_site_worker import WorkerConfig, check_database_identity

_stop = False


def request_stop(_signum, _frame):
    global _stop
    _stop = True


def run(*, manifest_document: dict, state: dict, host: str, index: int,
        duration_seconds: float, interval_seconds: float, max_iterations: int,
        execute: bool, url: str | None, monotonic=time.monotonic,
        sleep=time.sleep) -> dict:
    """Bounded, serialized synthetic lease cycles with token-fenced release."""
    manifest = validate_manifest_document(manifest_document)
    validate_state(manifest, state)
    if not 0 < duration_seconds <= 14400:
        raise ValueError("duration must be within (0, 14400] seconds")
    if not 0.1 <= interval_seconds <= 3600:
        raise ValueError("interval must be 0.1..3600 seconds")
    if not 1 <= max_iterations <= 100000:
        raise ValueError("max iterations must be 1..100000")
    count = manifest.distribution.get(host, 0)
    if count < 1:
        raise ValueError("host not enabled in manifest")
    worker = WorkerConfig.build(host=host, worker_index=index,
                                workers_on_host=count, run_id=manifest.run_id)
    report = {
        "run_id": manifest.run_id, "manifest_sha256": manifest.report()["sha256"],
        "host": host, "worker_index": index,
        "collector_uuid": str(worker.collector_uuid),
        "mode": "synthetic-d2-soak" if execute else "dry-run",
        "http_requests": 0, "claims": 0, "releases": 0,
        "empty_polls": 0, "lease_losses": 0, "iterations": 0,
        "duration_seconds": duration_seconds,
    }
    if not execute:
        return report
    if not url:
        raise ValueError("BF4PS_STAGE9C_D2_URL required")
    check_database_identity(url)
    engine = create_engine(url, connect_args={"connect_timeout": 5},
                           pool_size=1, max_overflow=0)
    try:
        with engine.connect() as conn:
            validate_claim_cohort(conn, run_id=manifest.run_id,
                                  soldier_ids=state["soldier_ids"],
                                  collector_uuid=worker.collector_uuid, host=host)
            conn.rollback()
        deadline = monotonic() + duration_seconds
        while not _stop and monotonic() < deadline and report["iterations"] < max_iterations:
            report["iterations"] += 1
            with engine.begin() as conn:
                job = claim_next_job(conn, collector_uuid=worker.collector_uuid,
                                     allowed_soldier_ids=state["soldier_ids"],
                                     resource="detailed", lane="background",
                                     lease_seconds=manifest.lease_seconds)
            if job is None:
                report["empty_polls"] += 1
            else:
                report["claims"] += 1
                with engine.begin() as conn:
                    running = mark_job_running(conn, job)
                    released = release_for_retry(conn, job, retry_after_seconds=1) if running else False
                if released:
                    report["releases"] += 1
                else:
                    report["lease_losses"] += 1
            remaining = deadline - monotonic()
            if remaining > 0 and not _stop:
                sleep(min(interval_seconds, remaining))
        report["status"] = "stopped" if _stop else "complete"
        return report
    finally:
        engine.dispose()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--worker-index", type=int, required=True)
    parser.add_argument("--duration-seconds", type=float, required=True)
    parser.add_argument("--interval-seconds", type=float, default=1.0)
    parser.add_argument("--max-iterations", type=int, default=100000)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    try:
        doc = json.loads(args.manifest.read_text())
        state = json.loads(args.state.read_text())
        report = run(manifest_document=doc, state=state,
                     host=socket.gethostname().split(".")[0].lower(),
                     index=args.worker_index,
                     duration_seconds=args.duration_seconds,
                     interval_seconds=args.interval_seconds,
                     max_iterations=args.max_iterations,
                     execute=args.execute,
                     url=os.environ.get("BF4PS_STAGE9C_D2_URL"))
        print(json.dumps(report, sort_keys=True), flush=True)
    except (OSError, ValueError, RuntimeError, TypeError, KeyError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
