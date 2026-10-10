"""Guarded D2 1295/1296 SQL-counted scratch ledger boundary race.

No HTTP, no collectors, no T4/production access. Inserts 1295 synthetic
ledger rows and two contenders; deletes only run-scoped rows in finally.
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
INSERT_BASE = text(
    "INSERT INTO outbound_dispatches "
    "(dispatch_id,job_id,attempt_number,resource,lease_token,collector_uuid,"
    "egress_key,lane,payload_fingerprint,admitted_at) "
    "VALUES (:dispatch_id,:job_id,1,'weapons',:lease_token,:collector_uuid,"
    ":egress_key,'background','synthetic-boundary-fixture',:at)"
)


def run(url: str) -> None:
    validate_target(url)
    engine = create_engine(url, pool_size=3, max_overflow=0, connect_args={"connect_timeout": 5})
    tag = uuid4().hex
    egress = "synthetic-boundary-" + tag
    base = 2000000000 + int(tag[:7], 16) * 2000
    candidates = [
        SyntheticDispatch(uuid4(), base + 1295 + i, 1, "weapons", uuid4(),
                          uuid4(), egress, "synthetic-boundary-no-http")
        for i in range(2)
    ]
    barrier = Barrier(2)
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
                raise RuntimeError("REFUSING nonempty D2 ledger")
            if conn.execute(text(
                "SELECT count(*) FROM collection_events WHERE lane='background' "
                "AND event_type='collection_attempt_started' "
                "AND occurred_at > clock_timestamp()-interval '1 hour'"
            )).scalar_one() != 0:
                raise RuntimeError("REFUSING active started evidence")
            if conn.execute(text(
                "SELECT count(*) FROM collection_jobs WHERE lane='background' "
                "AND status IN ('claimed','running') AND lease_expires_at > clock_timestamp()"
            )).scalar_one() != 0:
                raise RuntimeError("REFUSING active reservations")
            conn.rollback()

        with engine.begin() as conn:
            conn.execute(LOCK)
            at = conn.execute(text("SELECT clock_timestamp()")).scalar_one()
            batch = [
                dict(dispatch_id=uuid4(), job_id=base + i, lease_token=uuid4(),
                     collector_uuid=uuid4(), egress_key=egress, at=at)
                for i in range(1295)
            ]
            conn.execute(INSERT_BASE, batch)
            counted = read_conservative_background_usage(conn, at=at)
            if counted != 1295:
                raise AssertionError(f"fixture SQL count={counted}, expected 1295")

        def contender(i: int) -> str:
            barrier.wait(timeout=20)
            with engine.begin() as conn:
                return "admitted" if try_synthetic_admission(conn, candidates[i]) else "denied"

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(contender, i) for i in range(2)]
            outcomes = [f.result(timeout=35) for f in futures]
        if sorted(outcomes) != ["admitted", "denied"]:
            raise AssertionError(f"unexpected outcomes: {outcomes}")
        with engine.begin() as conn:
            conn.execute(LOCK)
            now = conn.execute(text("SELECT clock_timestamp()")).scalar_one()
            counted = read_conservative_background_usage(conn, at=now)
            owned = conn.execute(text(
                "SELECT count(*) FROM outbound_dispatches WHERE egress_key=:egress"
            ), {"egress": egress}).scalar_one()
            if counted != 1296 or owned != 1296:
                raise AssertionError(f"post-race SQL count={counted}, fixture rows={owned}")
        print("PASS: 1295 actual synthetic ledger rows + 2 concurrent contenders; one admitted, one denied")
        print("PASS: post-race real SQL usage=1296; run-scoped ledger rows=1296")
        print("LIMIT: D2 scratch only, no physical HTTP dispatch or production admission")
    finally:
        try:
            with engine.begin() as conn:
                conn.execute(LOCK)
                conn.execute(text(
                    "DELETE FROM outbound_dispatches WHERE egress_key=:egress "
                    "AND job_id >= :base AND job_id < :end "
                    "AND payload_fingerprint IN ('synthetic-boundary-fixture','synthetic-boundary-no-http')"
                ), {"egress": egress, "base": base, "end": base + 1297})
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
