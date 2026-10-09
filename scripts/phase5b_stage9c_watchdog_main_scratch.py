#!/usr/bin/env python3
"""Exercise watchdog main() against allowlisted scratch PostgreSQL and TEMP tables.

No real collectors, systemd, migrations or HTTP. Requires --execute.
Persistent writes: disposable Stage 9C supervision rows, deleted in finally.
"""
from __future__ import annotations

import argparse
import os
import sys
from contextlib import contextmanager
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import create_engine, text

from bf4ps.stage9c_supervision import CUTOVER_AT, BOUNDARY_EVENT_ID
from scripts import phase5b_stage9c_watchdog as watchdog
from scripts.phase5b_stage9c_abort_drain_scratch import check, create_run, state
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
        print("DRY RUN: scratch-only watchdog main() with TEMP shadows")
        return

    engine = create_engine(url, pool_pre_ping=True, connect_args={
        "connect_timeout": 5,
        "options": "-c statement_timeout=10000 -c lock_timeout=1000",
    })
    originals = (watchdog.validate_target, watchdog.IDENTITIES,
                 watchdog.create_engine, watchdog.database_url,
                 watchdog.signal.signal, watchdog.STOP, sys.argv)
    run_ids = []
    try:
        with engine.connect() as conn:
            check(conn)
            conn.rollback()

            def scratch_validate(c):
                row = c.execute(text(
                    "SELECT current_database(), current_user, inet_server_addr(), "
                    "pg_is_in_recovery(), current_setting('transaction_read_only')"
                )).one()
                if (row[0], row[1], str(row[2]), row[3], row[4]) != (
                    EXPECTED_DATABASE, EXPECTED_USER, EXPECTED_IP, False, "off"
                ):
                    raise RuntimeError("REFUSING unsafe scratch identity")
                if c.execute(text("SELECT version_num FROM alembic_version")).scalar_one() != "0004_stage9c_supervision_runs":
                    raise RuntimeError("REFUSING unsafe scratch revision")

            watchdog.validate_target = scratch_validate
            watchdog.IDENTITIES = {
                uuid4(): (f"scratch-main-{i}", f"scratch-main-host-{i}", f"scratch-main-egress-{i}")
                for i in range(3)
            }
            conn.execute(text("""
                CREATE TEMP TABLE collectors (
                    collector_uuid uuid PRIMARY KEY, collector_name text,
                    hostname text, egress_key text, lane text, retired_at timestamptz,
                    drained boolean NOT NULL DEFAULT false,
                    updated_at timestamptz NOT NULL DEFAULT now()
                ) ON COMMIT PRESERVE ROWS
            """))
            conn.execute(text("""
                CREATE TEMP TABLE collection_events (
                    event_id bigint PRIMARY KEY, occurred_at timestamptz NOT NULL,
                    event_type text NOT NULL, collector_uuid uuid, job_id bigint,
                    attempt_number integer, http_status integer, error_class text,
                    lane text, resource text
                ) ON COMMIT PRESERVE ROWS
            """))
            conn.execute(text("""
                CREATE TEMP TABLE collection_jobs (
                    lane text, resource text, reason text, eligible_at timestamptz
                ) ON COMMIT PRESERVE ROWS
            """))
            for uid, (name, host, egress) in watchdog.IDENTITIES.items():
                conn.execute(text("""
                    INSERT INTO pg_temp.collectors
                    (collector_uuid,collector_name,hostname,egress_key,lane)
                    VALUES (:uid,:name,:host,:egress,'background')
                """), {"uid": uid, "name": name, "host": host, "egress": egress})
            conn.commit()

            class BoundEngine:
                @contextmanager
                def begin(self):
                    with conn.begin():
                        yield conn
                def dispose(self):
                    pass

            watchdog.create_engine = lambda *_a, **_kw: BoundEngine()
            watchdog.database_url = lambda: "scratch-url-never-used"
            watchdog.signal.signal = lambda *_a, **_kw: None

            def invoke(run_id, owner):
                sys.argv = [
                    "watchdog", "--run-id", str(run_id),
                    "--watchdog-owner", str(owner),
                    "--watchdog-generation", "1",
                    "--cutover-at", CUTOVER_AT,
                    "--since-event-id", str(BOUNDARY_EVENT_ID),
                    "--once", "--armed",
                ]
                watchdog.STOP = False
                return watchdog.main()

            # Healthy main: lease renewal, no abort or drain.
            run_id, owner = uuid4(), uuid4()
            run_ids.append(run_id)
            create_run(conn, run_id, owner)
            conn.commit()
            assert invoke(run_id, owner) == 0
            assert state(conn, run_id) == "active"
            assert conn.execute(text(
                "SELECT count(*) FROM pg_temp.collectors WHERE drained"
            )).scalar_one() == 0
            conn.rollback()
            print("PASS: real PostgreSQL watchdog main() healthy inspection + fenced renewal")

            # Seed saturated trailing-hour context before supervision; no
            # trial starts. Current-hour check must abort at 1297.
            now = conn.execute(text("SELECT now()")).scalar_one()
            conn.rollback()
            conn.execute(text("""
                INSERT INTO pg_temp.collection_events
                (event_id,occurred_at,event_type,lane,resource)
                SELECT n,:stamp,'collection_attempt_started','background','detailed'
                FROM generate_series(1,1297) n
            """), {"stamp": now - timedelta(minutes=1)})
            run_id, owner = uuid4(), uuid4()
            run_ids.append(run_id)
            create_run(conn, run_id, owner)
            conn.commit()
            assert invoke(run_id, owner) == 2
            assert state(conn, run_id) == "aborted"
            reason = conn.execute(text(
                "SELECT abort_reason FROM stage9c_supervision_runs WHERE run_id=:id"
            ), {"id": run_id}).scalar_one()
            assert "1297>1296" in reason, reason
            assert conn.execute(text(
                "SELECT count(*) FROM pg_temp.collectors WHERE drained"
            )).scalar_one() == 3
            conn.rollback()
            print("PASS: real PostgreSQL watchdog main() budget abort + atomic TEMP drain")

            # Drift: combined abort/drain must roll back, then main() must
            # commit sticky fallback abort without claiming fleet drain.
            conn.execute(text("UPDATE pg_temp.collectors SET drained=false"))
            first_uid = next(iter(watchdog.IDENTITIES))
            conn.execute(text(
                "UPDATE pg_temp.collectors SET hostname='drifted' WHERE collector_uuid=:uid"
            ), {"uid": first_uid})
            run_id, owner = uuid4(), uuid4()
            run_ids.append(run_id)
            create_run(conn, run_id, owner)
            conn.commit()
            assert invoke(run_id, owner) == 2
            assert state(conn, run_id) == "aborted"
            reason = conn.execute(text(
                "SELECT abort_reason FROM stage9c_supervision_runs WHERE run_id=:id"
            ), {"id": run_id}).scalar_one()
            assert "fleet drain failed" in reason, reason
            assert conn.execute(text(
                "SELECT count(*) FROM pg_temp.collectors WHERE drained"
            )).scalar_one() == 0
            conn.rollback()
            print("PASS: real PostgreSQL watchdog main() rollback + sticky fallback; TEMP fleet undrained")

            with conn.begin():
                for rid in run_ids:
                    assert conn.execute(text(
                        "DELETE FROM stage9c_supervision_runs WHERE run_id=:id"
                    ), {"id": rid}).rowcount == 1
            run_ids.clear()
            assert conn.execute(text(
                "SELECT count(*) FROM stage9c_supervision_runs"
            )).scalar_one() == 0
            conn.rollback()
            print("PASS: scratch supervision ledger cleaned; TEMP shadows session-scoped")
    finally:
        (watchdog.validate_target, watchdog.IDENTITIES,
         watchdog.create_engine, watchdog.database_url,
         watchdog.signal.signal, watchdog.STOP, sys.argv) = originals
        if run_ids:
            try:
                with engine.begin() as cleanup:
                    for rid in run_ids:
                        cleanup.execute(text(
                            "DELETE FROM stage9c_supervision_runs WHERE run_id=:id"
                        ), {"id": rid})
            except Exception as exc:
                print(f"WARNING: scratch cleanup failed for disposable run IDs: {exc}")
        engine.dispose()


if __name__ == "__main__":
    main()
