#!/usr/bin/env python3
"""Non-destructive Stage 9C transaction fault injection on existing scratch 0004.

Explicit scratch URL only. Uses transaction-local temporary collector table,
never writes public.collectors. No migrations, systemd or HTTP requests.
"""
from __future__ import annotations

import argparse
import os
from uuid import uuid4

from sqlalchemy import create_engine, text

from bf4ps.stage9c_supervision import (
    CUTOVER_AT, BOUNDARY_EVENT_ID, SupervisionRefused,
    abort_owned_run, renew_after_inspection, require_guard_lease,
)
from scripts.phase5b_stage9c_postgres_integration import (
    EXPECTED_DATABASE, EXPECTED_USER, EXPECTED_IP, REV4, refuse_unsafe_target,
)
from scripts.phase5b_stage9c_watchdog import drain_fleet
from bf4ps.production_hosts import HOSTS


def validate(conn):
    identity = conn.execute(text(
        "SELECT current_database(), current_user, inet_server_addr(), "
        "pg_is_in_recovery(), current_setting('transaction_read_only')"
    )).one()
    expected = (EXPECTED_DATABASE, EXPECTED_USER, EXPECTED_IP, False, "off")
    if (identity[0], identity[1], str(identity[2]), identity[3], identity[4]) != expected:
        raise RuntimeError("REFUSING: scratch server/database/user/primary identity mismatch")
    revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    if revision != REV4:
        raise RuntimeError(f"REFUSING: scratch revision {revision!r} is not {REV4}")


def prepare(conn):
    # TEMP shadows public.collectors in this connection only.
    conn.execute(text("""
        CREATE TEMP TABLE collectors (
            collector_uuid uuid PRIMARY KEY,
            collector_name text NOT NULL,
            hostname text NOT NULL,
            egress_key text NOT NULL,
            lane text NOT NULL,
            retired_at timestamptz,
            drained boolean NOT NULL DEFAULT false,
            updated_at timestamptz
        ) ON COMMIT PRESERVE ROWS
    """))
    for hostname, host in HOSTS.items():
        conn.execute(text("""
            INSERT INTO pg_temp.collectors
            (collector_uuid,collector_name,hostname,egress_key,lane)
            VALUES (:uuid,:name,:hostname,:egress,'background')
        """), {"uuid": host.collector_uuid, "name": host.collector_name,
               "hostname": hostname, "egress": host.egress_key})


def insert_run(conn, run_id, owner):
    conn.execute(text("""
        INSERT INTO stage9c_supervision_runs
        (run_id,state,cutover_at,since_event_id,started_at,deadline_at,
         watchdog_owner,watchdog_generation,heartbeat_at,lease_expires_at)
        VALUES (:run_id,'active',CAST(:cutover AS timestamptz),:boundary,
                clock_timestamp(),clock_timestamp()+interval '6 hours',
                :owner,1,clock_timestamp(),clock_timestamp()+interval '20 seconds')
    """), {"run_id": run_id, "cutover": CUTOVER_AT,
           "boundary": BOUNDARY_EVENT_ID, "owner": owner})


def run(url):
    refuse_unsafe_target(url)
    engine = create_engine(url, pool_pre_ping=True, connect_args={
        "connect_timeout": 3, "options": "-c statement_timeout=3000 -c lock_timeout=1000"
    })
    run_id, owner = uuid4(), uuid4()
    try:
        # One connection: temporary table is invisible to every other session.
        with engine.connect() as conn:
            validate(conn)
            prepare(conn)
            conn.commit()

            # Establish isolated scratch supervision row, committed so the
            # next transaction can prove its abort rolls back.
            with conn.begin():
                insert_run(conn, run_id, owner)
                require_guard_lease(conn, run_id)

            try:
                with conn.begin():
                    abort_owned_run(conn, run_id=run_id, owner=owner,
                                    generation=1, reason="rollback injection")
                    assert drain_fleet(conn) == len(HOSTS)
                    raise RuntimeError("INTENTIONAL ROLLBACK")
            except RuntimeError as exc:
                if str(exc) != "INTENTIONAL ROLLBACK":
                    raise
            with conn.begin():
                state = conn.execute(text(
                    "SELECT state FROM stage9c_supervision_runs WHERE run_id=:id"
                ), {"id": run_id}).scalar_one()
                drained = conn.execute(text(
                    "SELECT count(*) FROM pg_temp.collectors WHERE drained"
                )).scalar_one()
                assert state == "active" and drained == 0, (state, drained)
            print("PASS: actual PostgreSQL rollback restored active run and undrained temporary fleet")

            with conn.begin():
                abort_owned_run(conn, run_id=run_id, owner=owner,
                                generation=1, reason="committed scratch abort")
                assert drain_fleet(conn) == len(HOSTS)
            with conn.begin():
                state = conn.execute(text(
                    "SELECT state FROM stage9c_supervision_runs WHERE run_id=:id"
                ), {"id": run_id}).scalar_one()
                drained = conn.execute(text(
                    "SELECT count(*) FROM pg_temp.collectors WHERE drained"
                )).scalar_one()
                assert state == "aborted" and drained == len(HOSTS)
                for operation in (
                    lambda: require_guard_lease(conn, run_id),
                    lambda: renew_after_inspection(
                        conn, run_id=run_id, owner=owner,
                        generation=1, inspection_passed=True),
                ):
                    try:
                        operation()
                    except SupervisionRefused:
                        pass
                    else:
                        raise AssertionError("aborted run unexpectedly accepted")
            print("PASS: actual PostgreSQL committed abort/drain; aborted lease cannot renew")
    finally:
        # Remove only our exact scratch run, even if a check fails.
        # No public collector rows were ever created or modified.
        try:
            with engine.begin() as cleanup:
                validate(cleanup)
                cleanup.execute(text(
                    "DELETE FROM stage9c_supervision_runs WHERE run_id=:id "
                    "AND watchdog_owner=:owner"
                ), {"id": run_id, "owner": owner})
        finally:
            engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    url = os.environ.get("BF4PS_STAGE9C_INTEGRATION_URL", "")
    if not url:
        parser.error("BF4PS_STAGE9C_INTEGRATION_URL is required")
    refuse_unsafe_target(url)
    if not args.execute:
        print("DRY RUN: would test transaction rollback on existing isolated scratch 0004")
        return
    run(url)


if __name__ == "__main__":
    main()
