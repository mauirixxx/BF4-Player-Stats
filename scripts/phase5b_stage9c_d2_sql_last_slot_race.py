"""D2 guarded real-SQL last-slot race, capacity=1, no HTTP.

Two independent transactions use the real three-source reconciliation query
and existing advisory lock. Synthetic ledger rows are cleaned by dispatch ID.
Not production admission; no queue ownership or physical-send guarantee.
"""
from __future__ import annotations

import argparse
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

from sqlalchemy import create_engine, text

from bf4ps.dispatch_admission_scratch import SyntheticDispatch, try_synthetic_admission
from bf4ps.dispatch_budget_sql import read_conservative_background_usage
from scripts.phase5b_stage9c_d2_ledger_integration import (
    EXPECTED_DB, EXPECTED_IP, EXPECTED_USER, HEAD, validate_target,
)

LOCK = text("SELECT pg_advisory_xact_lock(hashtext('bf4ps:phase5b-background-service'))")


def run(url: str) -> None:
    validate_target(url)
    engine = create_engine(url, pool_size=3, max_overflow=0, connect_args={"connect_timeout": 5})
    barrier = Barrier(2)
    run_id = uuid4().hex
    job_base = 1100000000 + int(run_id[:7], 16) * 2
    egress = "synthetic-sql-race-" + run_id
    candidates = [
        SyntheticDispatch(uuid4(), job_base + i, 1, "weapons", uuid4(),
                          uuid4(), egress, "synthetic-no-http")
        for i in range(2)
    ]
    ids = [candidate.dispatch_id for candidate in candidates]
    try:
        with engine.connect() as conn:
            identity = conn.execute(text(
                "SELECT current_database(),current_user,inet_server_addr(),"
                "pg_is_in_recovery(),current_setting('transaction_read_only')"
            )).one()
            if (identity[0], identity[1], str(identity[2]), identity[3], identity[4]) != (
                EXPECTED_DB, EXPECTED_USER, EXPECTED_IP, False, "off"
            ):
                raise RuntimeError("REFUSING unexpected D2 database identity")
            if conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() != HEAD:
                raise RuntimeError("REFUSING unexpected D2 migration head")
            if conn.execute(text("SELECT count(*) FROM outbound_dispatches")).scalar_one() != 0:
                raise RuntimeError("REFUSING nonempty D2 dispatch ledger")
            if conn.execute(text(
                "SELECT count(*) FROM collection_events WHERE lane='background' "
                "AND event_type='collection_attempt_started' "
                "AND occurred_at > clock_timestamp()-interval '1 hour'"
            )).scalar_one() != 0:
                raise RuntimeError("REFUSING active started events")
            if conn.execute(text(
                "SELECT count(*) FROM collection_jobs WHERE lane='background' "
                "AND status IN ('claimed','running') AND lease_expires_at > clock_timestamp()"
            )).scalar_one() != 0:
                raise RuntimeError("REFUSING active reservations")
            conn.rollback()

        def contender(index: int) -> str:
            barrier.wait(timeout=15)
            with engine.begin() as conn:
                allowed = try_synthetic_admission(conn, candidates[index], capacity=1)
                return "admitted" if allowed else "denied"

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(contender, i) for i in range(2)]
            outcomes = [future.result(timeout=25) for future in futures]
        if sorted(outcomes) != ["admitted", "denied"]:
            raise AssertionError(f"unexpected outcomes: {outcomes}")
        with engine.begin() as conn:
            conn.execute(LOCK)
            stamp = conn.execute(text("SELECT clock_timestamp()")).scalar_one()
            counted = read_conservative_background_usage(conn, at=stamp)
            rows = conn.execute(text(
                "SELECT count(*) FROM outbound_dispatches "
                "WHERE dispatch_id IN (:a,:b) AND egress_key=:egress"
            ), {"a": ids[0], "b": ids[1], "egress": egress}).scalar_one()
            if counted != 1 or rows != 1:
                raise AssertionError(f"counted={counted}, synthetic_rows={rows}")
        print("PASS: two independent connections, real SQL count, capacity=1, one admitted, one denied")
        print("LIMIT: scratch-only capacity=1, no real HTTP or production admission")
    finally:
        try:
            with engine.begin() as conn:
                conn.execute(LOCK)
                conn.execute(text(
                    "DELETE FROM outbound_dispatches "
                    "WHERE dispatch_id IN (:a,:b) AND egress_key=:egress"
                ), {"a": ids[0], "b": ids[1], "egress": egress})
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
