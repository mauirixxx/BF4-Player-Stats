#!/usr/bin/env python3
"""Scratch PostgreSQL: budget violation -> fenced abort + TEMP fleet drain.

No live collectors, Battlelog calls, migrations, or systemd. The only
persistent writes are disposable supervision-run records, removed in finally.
"""
from __future__ import annotations

import argparse
import os
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import create_engine, text

from bf4ps.stage9c_supervision import (
    SupervisionRefused, abort_owned_run, require_guard_lease,
)
from scripts import phase5b_stage9c_watchdog as watchdog
from scripts.phase5b_stage9c_abort_drain_scratch import check, create_run
from scripts.phase5b_stage9c_postgres_integration import (
    EXPECTED_DATABASE, EXPECTED_IP, EXPECTED_USER, refuse_unsafe_target,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    url = os.environ.get("BF4PS_STAGE9C_INTEGRATION_URL", "")
    if not url:
        parser.error("BF4PS_STAGE9C_INTEGRATION_URL required")
    refuse_unsafe_target(url)
    if not args.execute:
        print("DRY RUN: allowlisted scratch PostgreSQL only")
        return

    engine = create_engine(url, pool_pre_ping=True, connect_args={
        "connect_timeout": 5,
        "options": "-c statement_timeout=10000 -c lock_timeout=1000",
    })
    original_validate, original_identities = watchdog.validate_target, watchdog.IDENTITIES
    run_id = None
    try:
        with engine.connect() as conn:
            check(conn)
            conn.rollback()
            # The actual SQL is exercised; only the target-name validator
            # and expected collector identities are replaced for scratch.
            def scratch_validate(c):
                identity = c.execute(text(
                    "SELECT current_database(), current_user, inet_server_addr(), "
                    "pg_is_in_recovery(), current_setting('transaction_read_only')"
                )).one()
                if (identity[0], identity[1], str(identity[2]), identity[3], identity[4]) != (
                    EXPECTED_DATABASE, EXPECTED_USER, EXPECTED_IP, False, "off"
                ):
                    raise RuntimeError("unsafe scratch target identity")
                rev = c.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                if rev != "0004_stage9c_supervision_runs":
                    raise RuntimeError("unsafe scratch revision")

            watchdog.validate_target = scratch_validate
            identities = {
                uuid4(): (f"scratch-collector-{i}", f"scratch-host-{i}", f"scratch-egress-{i}")
                for i in range(3)
            }
            watchdog.IDENTITIES = identities
            conn.execute(text("""
                CREATE TEMP TABLE collectors (
                    collector_uuid uuid PRIMARY KEY, collector_name text,
                    hostname text, egress_key text, lane text,
                    retired_at timestamptz, drained boolean NOT NULL DEFAULT false,
                    updated_at timestamptz NOT NULL DEFAULT now()
                ) ON COMMIT PRESERVE ROWS
            """))
            conn.execute(text("""
                CREATE TEMP TABLE collection_events (
                    event_id bigint PRIMARY KEY, occurred_at timestamptz NOT NULL,
                    event_type text NOT NULL, collector_uuid uuid,
                    job_id bigint, attempt_number integer, http_status integer,
                    error_class text, lane text, resource text
                ) ON COMMIT PRESERVE ROWS
            """))
            conn.execute(text("""
                CREATE TEMP TABLE collection_jobs (
                    lane text, resource text, reason text, eligible_at timestamptz
                ) ON COMMIT PRESERVE ROWS
            """))
            for uid, (name, host, egress) in identities.items():
                conn.execute(text("""
                    INSERT INTO pg_temp.collectors
                    (collector_uuid, collector_name, hostname, egress_key, lane)
                    VALUES (:id, :name, :host, :egress, 'background')
                """), {"id": uid, "name": name, "host": host, "egress": egress})
            conn.commit()

            # Synthetic audit clock for events; immutable supervision
            # boundary remains the frozen Stage 9B value.
            now = conn.execute(text("SELECT now()")).scalar_one()
            conn.rollback()
            cutover = now - timedelta(minutes=10)
            boundary = 11558
            collector_uuid = next(iter(identities))
            conn.execute(text("""
                INSERT INTO pg_temp.collection_events
                (event_id, occurred_at, event_type, lane, resource)
                SELECT n, :stamp, 'collection_attempt_started',
                       'background', 'detailed'
                FROM generate_series(1,1296) AS n
            """), {"stamp": cutover - timedelta(seconds=1)})
            conn.execute(text("""
                INSERT INTO pg_temp.collection_events
                (event_id, occurred_at, event_type, lane, resource,
                 collector_uuid, job_id, attempt_number)
                VALUES
                (11559, :stamp, 'collection_attempt_started',
                 'background', 'detailed', :collector, 42, 1),
                (11560, :stamp, 'collection_success',
                 'background', 'detailed', :collector, 42, 1)
            """), {"stamp": cutover + timedelta(seconds=1), "collector": collector_uuid})
            run_id, owner = uuid4(), uuid4()
            create_run(conn, run_id, owner)
            conn.commit()

            # This is the same transactional sequence used in armed main().
            with conn.begin():
                require_guard_lease(conn, run_id)
                issues, starts, terminals, maximum = watchdog.inspect(
                    conn, boundary=boundary, cutover=cutover, grace_seconds=150
                )
                assert (starts, terminals, maximum) == (1, 1, 1297)
                assert issues == ["rolling budget exceeded 1297>1296"], issues
                abort_owned_run(
                    conn, run_id=run_id, owner=owner, generation=1,
                    reason="; ".join(issues),
                )
                assert watchdog.drain_fleet(conn) == 3
            print("PASS: PostgreSQL budget violation committed fenced abort + TEMP fleet drain")

            row = conn.execute(text("""
                SELECT state, abort_reason FROM stage9c_supervision_runs
                WHERE run_id=:id
            """), {"id": run_id}).one()
            assert row[0] == "aborted" and "1297>1296" in row[1]
            assert conn.execute(text(
                "SELECT count(*) FROM pg_temp.collectors WHERE drained"
            )).scalar_one() == 3
            conn.rollback()
            print("PASS: abort reason durable and all three TEMP collectors drained")

            # Stale owner cannot modify a new active run, including drain.
            # No second run is created: an already-aborted run must reject
            # even the original owner and a forged owner.
            for candidate in (owner, uuid4()):
                try:
                    with conn.begin():
                        abort_owned_run(
                            conn, run_id=run_id, owner=candidate, generation=1,
                            reason="must refuse replay",
                        )
                except SupervisionRefused:
                    pass
                else:
                    raise AssertionError("replayed/stale abort accepted")
            assert conn.execute(text("""
                SELECT state FROM stage9c_supervision_runs WHERE run_id=:id
            """), {"id": run_id}).scalar_one() == "aborted"
            conn.rollback()
            print("PASS: terminal run refuses replay and foreign owner")

            with conn.begin():
                assert conn.execute(text("""
                    DELETE FROM stage9c_supervision_runs WHERE run_id=:id
                """), {"id": run_id}).rowcount == 1
            run_id = None
            assert conn.execute(text(
                "SELECT count(*) FROM stage9c_supervision_runs"
            )).scalar_one() == 0
            conn.rollback()
            print("PASS: scratch supervision ledger cleaned; TEMP tables session-scoped")
    finally:
        watchdog.validate_target, watchdog.IDENTITIES = original_validate, original_identities
        if run_id is not None:
            try:
                with engine.begin() as cleanup:
                    cleanup.execute(text(
                        "DELETE FROM stage9c_supervision_runs WHERE run_id=:id"
                    ), {"id": run_id})
            except Exception as exc:
                print(f"WARNING: scratch cleanup failed for run {run_id}: {exc}")
        engine.dispose()


if __name__ == "__main__":
    main()
