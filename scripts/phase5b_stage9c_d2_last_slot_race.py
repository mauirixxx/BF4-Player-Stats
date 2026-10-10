"""D2 synthetic last-slot race using the existing background advisory authority.

This is a transaction-serialization experiment, NOT production admission code.
The synthetic base usage 1295 is a fixture, not a measurement of existing jobs.
No HTTP, no workers, no production or T4 writes.
"""
from __future__ import annotations

import argparse
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

from sqlalchemy import create_engine, text
from scripts.phase5b_stage9c_d2_ledger_integration import (
    EXPECTED_DB, EXPECTED_IP, EXPECTED_USER, HEAD, validate_target,
)

LOCK = text("SELECT pg_advisory_xact_lock(hashtext('bf4ps:phase5b-background-service'))")
INSERT = text(
    "INSERT INTO outbound_dispatches "
    "(dispatch_id,job_id,attempt_number,resource,lease_token,collector_uuid,"
    "egress_key,lane,payload_fingerprint,admitted_at) "
    "VALUES (:id,:job,1,'weapons',:lease,:collector,'synthetic-last-slot',"
    "'background','synthetic-only',clock_timestamp())"
)


def run(url: str) -> None:
    validate_target(url)
    engine = create_engine(url, pool_size=3, max_overflow=0, connect_args={"connect_timeout": 5})
    run_tag = uuid4().hex
    job_base = 900000000 + int(run_tag[:6], 16)
    barrier = Barrier(2)
    try:
        with engine.connect() as conn:
            observed = conn.execute(text(
                "SELECT current_database(),current_user,inet_server_addr(),"
                "pg_is_in_recovery(),current_setting('transaction_read_only')"
            )).one()
            if (observed[0], observed[1], str(observed[2]), observed[3], observed[4]) != (
                EXPECTED_DB, EXPECTED_USER, EXPECTED_IP, False, "off"
            ):
                raise RuntimeError("REFUSING unexpected D2 database identity")
            if conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() != HEAD:
                raise RuntimeError("REFUSING D2 revision mismatch")
            if conn.execute(text("SELECT count(*) FROM outbound_dispatches")).scalar_one() != 0:
                raise RuntimeError("REFUSING nonempty dispatch ledger")

        def contender(index: int) -> str:
            barrier.wait(timeout=15)
            with engine.begin() as conn:
                conn.execute(LOCK)
                # Sample PostgreSQL time AFTER the advisory lock. The fixture
                # represents 1295 existing admissions, not database records.
                stamp = conn.execute(text("SELECT clock_timestamp()")).scalar_one()
                admitted = conn.execute(text(
                    "SELECT count(*) FROM outbound_dispatches "
                    "WHERE egress_key='synthetic-last-slot' AND lane='background' "
                    "AND admitted_at >= :cutoff"
                ), {"cutoff": stamp.replace(year=stamp.year - 1)}).scalar_one()
                if 1295 + admitted >= 1296:
                    return "denied"
                conn.execute(INSERT, dict(
                    id=uuid4(), job=job_base + index, lease=uuid4(), collector=uuid4(),
                ))
                return "admitted"

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = [f.result(timeout=20) for f in (
                executor.submit(contender, 0), executor.submit(contender, 1)
            )]
        if sorted(results) != ["admitted", "denied"]:
            raise AssertionError(f"unexpected outcomes: {results}")
        with engine.connect() as conn:
            count = conn.execute(text(
                "SELECT count(*) FROM outbound_dispatches "
                "WHERE job_id IN (:a,:b) AND egress_key='synthetic-last-slot'"
            ), {"a": job_base, "b": job_base + 1}).scalar_one()
            assert count == 1, count
        print("PASS: shared advisory lock, synthetic 1295/1296 baseline, one admitted, one denied")
        print("LIMIT: fixture-only budget, not real collector reconciliation or actual HTTP")
    finally:
        with engine.begin() as conn:
            conn.execute(LOCK)
            conn.execute(text(
                "DELETE FROM outbound_dispatches "
                "WHERE job_id IN (:a,:b) AND egress_key='synthetic-last-slot'"
            ), {"a": job_base, "b": job_base + 1})
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
