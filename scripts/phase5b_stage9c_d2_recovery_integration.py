"""Guarded real D2 crash-recovery proof; no HTTP.

Simulates missing coordinator state in memory, recovering solely from committed
synthetic PostgreSQL rows. Uses scoped cleanup in finally.
"""
from __future__ import annotations

import argparse
import os
from uuid import uuid4

from sqlalchemy import create_engine

from scripts.phase5b_three_site_manifest import RunManifest
from scripts.phase5b_three_site_d2_coordinator import prepare, verify, cleanup, assert_clean
from scripts.phase5b_three_site_recovery import recover_state
from scripts.phase5b_three_site_worker import check_database_identity


def run(url: str):
    check_database_identity(url)
    engine = create_engine(url, connect_args={"connect_timeout": 5})
    manifest = RunManifest.build(
        run_id="d2recovery_" + uuid4().hex,
        distribution={"tcou": 1, "kah-01": 1, "hnl-01": 1},
        job_count=3)
    original = None
    try:
        with engine.begin() as conn:
            original = prepare(conn, manifest)
        # No original state is passed to recovery: simulate crash after COMMIT
        # but before the coordinator publishes its state file.
        with engine.connect() as conn:
            recovered = recover_state(conn, manifest)
            conn.rollback()
        if recovered != original:
            raise AssertionError("recovered cohort differs from committed cohort")
        with engine.connect() as conn:
            report = verify(conn, manifest, recovered)
            conn.rollback()
        if report["jobs"] != 3 or report["claimed"] != 0:
            raise AssertionError("unexpected recovered cohort state")
        print("PASS: real D2 post-commit state recovery; 3 synthetic jobs")
    finally:
        try:
            if original is not None:
                with engine.begin() as conn:
                    cleaned = cleanup(conn, manifest, original)
                if any(cleaned.values()):
                    raise AssertionError("D2 scratch cleanup incomplete")
                print("PASS: D2 scoped cleanup; all five core tables empty")
        finally:
            engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        parser.error("--execute required")
    url = os.environ.get("BF4PS_STAGE9C_D2_URL")
    if not url:
        parser.error("BF4PS_STAGE9C_D2_URL required")
    run(url)
