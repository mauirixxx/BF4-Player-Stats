#!/usr/bin/env python3
"""Scratch-only PostgreSQL integration of the complete Stage 9C inspect() path.

No persistent writes, migrations, systemd, collectors or HTTP. All operational
tables referenced by inspect() are session-local PostgreSQL TEMP shadows.
"""
from __future__ import annotations

import argparse
import os
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import create_engine, text

from scripts import phase5b_stage9c_watchdog as watchdog
from scripts.phase5b_stage9c_abort_drain_scratch import check
from scripts.phase5b_stage9c_postgres_integration import refuse_unsafe_target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    url = os.environ.get("BF4PS_STAGE9C_INTEGRATION_URL", "")
    if not url:
        parser.error("BF4PS_STAGE9C_INTEGRATION_URL required")
    refuse_unsafe_target(url)
    if not args.execute:
        print("DRY RUN: scratch allowlist, TEMP shadows only")
        return

    engine = create_engine(url, pool_pre_ping=True, connect_args={
        "connect_timeout": 5, "options": "-c statement_timeout=10000",
    })
    original_validate = watchdog.validate_target
    original_identities = watchdog.IDENTITIES
    try:
        with engine.connect() as conn:
            check(conn)
            conn.rollback()
            conn.execute(text("""
                CREATE TEMP TABLE collection_events (
                    event_id bigint PRIMARY KEY,
                    occurred_at timestamptz NOT NULL,
                    event_type text NOT NULL,
                    collector_uuid uuid,
                    job_id bigint,
                    attempt_number integer,
                    http_status integer,
                    error_class text,
                    lane text,
                    resource text
                ) ON COMMIT PRESERVE ROWS
            """))
            conn.execute(text("""
                CREATE TEMP TABLE collection_jobs (
                    lane text, resource text, reason text, eligible_at timestamptz
                ) ON COMMIT PRESERVE ROWS
            """))
            conn.execute(text("""
                CREATE TEMP TABLE collectors (
                    collector_uuid uuid PRIMARY KEY, collector_name text,
                    hostname text, egress_key text, lane text, retired_at timestamptz
                ) ON COMMIT PRESERVE ROWS
            """))
            identities = {}
            for index in range(3):
                uid = uuid4()
                name, host, egress = (
                    f"scratch-inspect-{index}", f"scratch-host-{index}",
                    f"scratch-egress-{index}",
                )
                identities[uid] = (name, host, egress)
                conn.execute(text("""
                    INSERT INTO pg_temp.collectors
                    (collector_uuid, collector_name, hostname, egress_key, lane)
                    VALUES (:id, :name, :host, :egress, 'background')
                """), {"id": uid, "name": name, "host": host, "egress": egress})
            conn.commit()
            watchdog.IDENTITIES = identities

            # The target was strictly verified before TEMP creation. Bypass
            # only the production database-name guard inside inspect(), not
            # the real PostgreSQL query logic.
            def scratch_validate(c):
                db = c.execute(text("SELECT current_database()")).scalar_one()
                if db != "bf4ps_scratch_stage9c_integration":
                    raise RuntimeError("scratch identity drift")
            watchdog.validate_target = scratch_validate

            now = conn.execute(text("SELECT now()")).scalar_one()
            conn.rollback()
            cutover = now - timedelta(minutes=10)
            boundary = 11558
            collector_uuid = next(iter(identities))

            def populate(pre_count):
                conn.execute(text("TRUNCATE pg_temp.collection_events"))
                conn.execute(text("""
                    INSERT INTO pg_temp.collection_events
                        (event_id, occurred_at, event_type, lane, resource)
                    SELECT n, :stamp, 'collection_attempt_started',
                           'background', 'detailed'
                    FROM generate_series(1, :count) AS n
                """), {
                    "stamp": cutover - timedelta(seconds=1),
                    "count": pre_count,
                })
                conn.execute(text("""
                    INSERT INTO pg_temp.collection_events
                        (event_id, occurred_at, event_type, lane, resource,
                         collector_uuid, job_id, attempt_number)
                    VALUES
                        (11559, :stamp, 'collection_attempt_started',
                         'background', 'detailed', :collector, 42, 1),
                        (11560, :stamp, 'collection_success',
                         'background', 'detailed', :collector, 42, 1)
                """), {
                    "stamp": cutover + timedelta(seconds=1),
                    "collector": collector_uuid,
                })
                conn.commit()

            populate(1296)
            issues, starts, terminals, maximum = watchdog.inspect(
                conn, boundary=boundary, cutover=cutover, grace_seconds=150,
            )
            assert (starts, terminals, maximum) == (1, 1, 1297)
            assert issues == ["rolling budget exceeded 1297>1296"], issues
            conn.rollback()
            print("PASS: complete inspect() detects 1297 cross-boundary starts")

            populate(1295)
            issues, starts, terminals, maximum = watchdog.inspect(
                conn, boundary=boundary, cutover=cutover, grace_seconds=150,
            )
            assert (issues, starts, terminals, maximum) == ([], 1, 1, 1296)
            conn.rollback()
            print("PASS: complete inspect() accepts 1296; reconciliation unchanged")

            # Force an actual SQL failure in the inspection event read.
            # The dedicated budget-query failure is tested by the separate
            # rolling-budget scratch harness; both must fail closed.
            conn.execute(text(
                "ALTER TABLE pg_temp.collection_events RENAME COLUMN "
                "occurred_at TO missing_occurred_at"
            ))
            conn.commit()
            try:
                watchdog.inspect(
                    conn, boundary=boundary, cutover=cutover, grace_seconds=150,
                )
            except Exception:
                conn.rollback()
                print("PASS: complete inspect() propagates missing event evidence")
            else:
                conn.rollback()
                raise AssertionError("inspection accepted missing event timestamp")

            for table in ("collection_events", "collection_jobs", "collectors"):
                assert conn.execute(text("""
                    SELECT count(*) FROM pg_catalog.pg_class
                    WHERE relname = :name
                      AND relnamespace = pg_my_temp_schema()
                """), {"name": table}).scalar_one() == 1
            conn.rollback()
            print("PASS: all inspection data confined to TEMP shadows")
    finally:
        watchdog.validate_target = original_validate
        watchdog.IDENTITIES = original_identities
        engine.dispose()


if __name__ == "__main__":
    main()
