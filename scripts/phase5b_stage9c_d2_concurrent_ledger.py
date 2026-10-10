"""Independent-connection D2 ledger race test; synthetic evidence only.

Runs against the dedicated already-migrated D2 scratch database. Explicit
--execute required. Never touches shared T4 scratch or issues HTTP.
"""
from __future__ import annotations

import argparse
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from scripts.phase5b_stage9c_d2_ledger_integration import (
    HEAD, EXPECTED_DB, EXPECTED_IP, EXPECTED_USER, validate_target,
)

INSERT = text(
    "INSERT INTO outbound_dispatches "
    "(dispatch_id,job_id,attempt_number,resource,lease_token,collector_uuid,"
    "egress_key,lane,payload_fingerprint,admitted_at) "
    "VALUES (:dispatch_id,:job_id,:attempt_number,:resource,:lease_token,"
    ":collector_uuid,:egress_key,:lane,:payload_fingerprint,clock_timestamp())"
)


def run(url: str) -> None:
    validate_target(url)
    engine = create_engine(url, pool_size=6, max_overflow=0, connect_args={"connect_timeout": 5})
    ids = []
    try:
        with engine.connect() as conn:
            identity = conn.execute(text(
                "SELECT current_database(),current_user,inet_server_addr(),"
                "pg_is_in_recovery(),current_setting('transaction_read_only')"
            )).one()
            assert (identity[0], identity[1], str(identity[2]), identity[3], identity[4]) == (
                EXPECTED_DB, EXPECTED_USER, EXPECTED_IP, False, "off"
            ), "REFUSING unexpected database identity"
            assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == HEAD
            assert conn.execute(text("SELECT count(*) FROM outbound_dispatches")).scalar_one() == 0, (
                "REFUSING nonempty D2 dispatch ledger"
            )

        # Both transactions begin independently and compete on the same
        # unique logical identity. PostgreSQL must commit exactly one.
        shared = dict(job_id=918273, attempt_number=1, resource="weapons",
                      lease_token=uuid4(), collector_uuid=uuid4(),
                      egress_key="synthetic-race", lane="background",
                      payload_fingerprint="synthetic-fingerprint")
        barrier = Barrier(2)

        def contender():
            own_id = uuid4()
            barrier.wait(timeout=10)
            try:
                with engine.begin() as conn:
                    conn.execute(INSERT, {**shared, "dispatch_id": own_id})
                return "committed", own_id
            except IntegrityError:
                return "duplicate_rejected", own_id

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(contender) for _ in range(2)]
            outcomes = [f.result(timeout=20) for f in futures]
        ids = [item[1] for item in outcomes]
        assert sorted(item[0] for item in outcomes) == ["committed", "duplicate_rejected"], outcomes
        with engine.connect() as conn:
            assert conn.execute(text(
                "SELECT count(*) FROM outbound_dispatches WHERE job_id=:job_id "
                "AND attempt_number=1 AND resource='weapons' AND lease_token=:token"
            ), {"job_id": shared["job_id"], "token": shared["lease_token"]}).scalar_one() == 1
        print("PASS: two independent connections, one committed identity, one duplicate rejected")
    finally:
        # Clean up ONLY synthetic rows belonging to this test, regardless of
        # whether its assertions pass. No general DELETE/TRUNCATE.
        if ids:
            with engine.begin() as conn:
                conn.execute(
                    text("DELETE FROM outbound_dispatches WHERE dispatch_id = ANY(:ids) "
                         "AND job_id=918273 AND egress_key='synthetic-race'"),
                    {"ids": ids},
                )
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
