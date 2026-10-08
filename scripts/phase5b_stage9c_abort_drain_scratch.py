#!/usr/bin/env python3
"""Stage 9C scratch-only PostgreSQL abort/drain fault injection.

No Alembic migration, network collection, systemd, or production collector rows.
Uses PostgreSQL TEMP collectors shadow table and disposable supervision run rows.
Requires explicit --execute and BF4PS_STAGE9C_INTEGRATION_URL.
"""
from __future__ import annotations

import argparse
import os
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import create_engine, text

from bf4ps.stage9c_supervision import (
    BOUNDARY_EVENT_ID, CUTOVER_AT, SupervisionRefused, abort_owned_run,
)
from scripts import phase5b_stage9c_watchdog as watchdog
from scripts.phase5b_stage9c_postgres_integration import (
    EXPECTED_DATABASE, EXPECTED_IP, EXPECTED_USER, refuse_unsafe_target,
)


def check(conn):
    identity = conn.execute(text(
        "SELECT current_database(), current_user, inet_server_addr(), "
        "pg_is_in_recovery(), current_setting('transaction_read_only')"
    )).one()
    if identity != (EXPECTED_DATABASE, EXPECTED_USER, __import__("ipaddress").ip_address(EXPECTED_IP), False, "off"):
        raise RuntimeError(f"REFUSING unsafe target identity: {identity}")
    revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    if revision != "0004_stage9c_supervision_runs":
        raise RuntimeError("REFUSING wrong Alembic revision")
    if conn.execute(text("SELECT count(*) FROM collectors")).scalar_one() != 0:
        raise RuntimeError("REFUSING nonempty real collector registry")
    if conn.execute(text("SELECT count(*) FROM stage9c_supervision_runs")).scalar_one() != 0:
        raise RuntimeError("REFUSING nonempty supervision run ledger")


def create_run(conn, run_id, owner):
    conn.execute(text("""
        INSERT INTO stage9c_supervision_runs
        (run_id,state,cutover_at,since_event_id,started_at,deadline_at,
         watchdog_owner,watchdog_generation,heartbeat_at,lease_expires_at)
        VALUES (:id,'active',CAST(:cutover AS timestamptz),:boundary,
                transaction_timestamp(),transaction_timestamp()+interval '6 hours',
                :owner,1,transaction_timestamp(),transaction_timestamp()+interval '20 seconds')
    """), {"id": run_id, "owner": owner, "cutover": CUTOVER_AT,
           "boundary": BOUNDARY_EVENT_ID})


def state(conn, run_id):
    return conn.execute(text(
        "SELECT state FROM stage9c_supervision_runs WHERE run_id=:id"
    ), {"id": run_id}).scalar_one()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    url = os.environ.get("BF4PS_STAGE9C_INTEGRATION_URL", "")
    if not url:
        parser.error("BF4PS_STAGE9C_INTEGRATION_URL required")
    refuse_unsafe_target(url)
    if not args.execute:
        print("DRY RUN: scratch-only, temporary collector registry, no persistent changes")
        return
    engine = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 5})
    # One physical connection keeps the TEMP table scoped to this test.
    # Each explicit transaction is independently committed or rolled back.
    original = watchdog.IDENTITIES
    run_ids = []
    try:
        with engine.connect() as conn:
            check(conn)
            conn.rollback()
            uuids = [uuid4() for _ in range(3)]
            watchdog.IDENTITIES = {
                uid: (f"stage9c-scratch-{i}", f"scratch-{i}", f"scratch-egress-{i}")
                for i, uid in enumerate(uuids)
            }
            conn.execute(text("""
                CREATE TEMP TABLE collectors (
                    collector_uuid uuid PRIMARY KEY,
                    collector_name text NOT NULL,
                    hostname text NOT NULL,
                    egress_key text NOT NULL,
                    lane text NOT NULL,
                    retired_at timestamptz,
                    drained boolean NOT NULL DEFAULT false,
                    updated_at timestamptz NOT NULL DEFAULT now()
                ) ON COMMIT PRESERVE ROWS
            """))
            for uid, (name, host, egress) in watchdog.IDENTITIES.items():
                conn.execute(text("""
                    INSERT INTO pg_temp.collectors
                    (collector_uuid,collector_name,hostname,egress_key,lane)
                    VALUES (:id,:name,:host,:egress,'background')
                """), {"id": uid, "name": name, "host": host, "egress": egress})
            conn.commit()

            # Normal atomic path: abort and drain commit together.
            run_id, owner = uuid4(), uuid4()
            run_ids.append(run_id)
            create_run(conn, run_id, owner)
            conn.commit()
            with conn.begin():
                abort_owned_run(conn, run_id=run_id, owner=owner,
                                generation=1, reason="scratch normal abort")
                assert watchdog.drain_fleet(conn) == 3
            assert state(conn, run_id) == "aborted"
            assert conn.execute(text(
                "SELECT count(*) FROM pg_temp.collectors WHERE drained"
            )).scalar_one() == 3
            conn.rollback()
            print("PASS: normal abort + all-three TEMP fleet drain committed")

            # Identity drift: the combined transaction must roll back.
            conn.execute(text("UPDATE pg_temp.collectors SET drained=false"))
            conn.execute(text(
                "UPDATE pg_temp.collectors SET hostname='drifted' WHERE collector_uuid=:id"
            ), {"id": uuids[0]})
            run_id, owner = uuid4(), uuid4()
            run_ids.append(run_id)
            create_run(conn, run_id, owner)
            conn.commit()
            try:
                with conn.begin():
                    abort_owned_run(conn, run_id=run_id, owner=owner,
                                    generation=1, reason="scratch combined attempt")
                    watchdog.drain_fleet(conn)
            except RuntimeError as exc:
                assert "identity drift" in str(exc), str(exc)
            else:
                raise AssertionError("drift did not refuse fleet drain")
            assert state(conn, run_id) == "active"
            assert conn.execute(text(
                "SELECT count(*) FROM pg_temp.collectors WHERE drained"
            )).scalar_one() == 0
            conn.rollback()
            args_fallback = SimpleNamespace(
                run_id=run_id, watchdog_owner=owner, watchdog_generation=1
            )
            # Use a connection-bound engine facade so fallback uses the same
            # physical PostgreSQL session and its TEMP collector shadow.
            class BoundEngine:
                def begin(self):
                    return conn.begin()
            # The production watchdog target validator expects the live test DB.
            # Override only the target check with the stricter scratch validator
            # during this isolated integration call.
            old_validate = watchdog.validate_target
            def scratch_validate(c):
                row = c.execute(text(
                    "SELECT current_database(), current_user, inet_server_addr()"
                )).one()
                assert (row[0], row[1], str(row[2])) == (
                    EXPECTED_DATABASE, EXPECTED_USER, EXPECTED_IP
                )
            watchdog.validate_target = scratch_validate
            try:
                watchdog.commit_fallback_abort(
                    BoundEngine(), args_fallback, ["scratch identity drift"],
                    RuntimeError("cannot drain: identity drift"),
                )
            finally:
                watchdog.validate_target = old_validate
            assert state(conn, run_id) == "aborted"
            assert conn.execute(text(
                "SELECT count(*) FROM pg_temp.collectors WHERE drained"
            )).scalar_one() == 0
            conn.rollback()
            print("PASS: drift rollback followed by committed fenced abort; no drain claimed")

            # Stale owner/generation cannot abort a fresh run.
            run_id, owner = uuid4(), uuid4()
            run_ids.append(run_id)
            create_run(conn, run_id, owner)
            conn.commit()
            for candidate, generation in ((uuid4(), 1), (owner, 2)):
                try:
                    with conn.begin():
                        abort_owned_run(conn, run_id=run_id, owner=candidate,
                                        generation=generation, reason="must refuse")
                except SupervisionRefused:
                    pass
                else:
                    raise AssertionError("stale writer accepted")
            assert state(conn, run_id) == "active"
            conn.rollback()
            print("PASS: stale owner and generation fenced")

            # Cleanup only our own run IDs, never other rows.
            with conn.begin():
                for rid in run_ids:
                    deleted = conn.execute(text(
                        "DELETE FROM stage9c_supervision_runs WHERE run_id=:id"
                    ), {"id": rid}).rowcount
                    assert deleted == 1
            assert conn.execute(text(
                "SELECT count(*) FROM stage9c_supervision_runs"
            )).scalar_one() == 0
            conn.rollback()
            print("PASS: scratch cleanup; supervision ledger restored to zero")
    finally:
        # On assertion failure, delete only run IDs created by this harness.
        # Never mask the original error with a cleanup exception.
        try:
            with engine.begin() as cleanup:
                for rid in run_ids:
                    cleanup.execute(text(
                        "DELETE FROM stage9c_supervision_runs WHERE run_id=:id"
                    ), {"id": rid})
        except Exception as cleanup_error:
            print(f"WARNING: scratch cleanup failed; inspect disposable run IDs: {run_ids}; {cleanup_error}")
        watchdog.IDENTITIES = original
        engine.dispose()


if __name__ == "__main__":
    main()
