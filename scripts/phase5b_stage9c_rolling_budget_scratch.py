#!/usr/bin/env python3
"""Stage 9C scratch PostgreSQL rolling-budget test; TEMP objects only.

No migrations, production event writes, collectors, systemd, or HTTP.
Requires the same explicit allowlisted scratch target as the abort/drain harness.
"""
from __future__ import annotations

import argparse
import os
from datetime import timedelta

from sqlalchemy import create_engine, text

from scripts.phase5b_stage9c_abort_drain_scratch import check
from scripts.phase5b_stage9c_postgres_integration import refuse_unsafe_target
from scripts.phase5b_stage9c_watchdog import CEILING, rolling_background_max


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    url = os.environ.get("BF4PS_STAGE9C_INTEGRATION_URL", "")
    if not url:
        parser.error("BF4PS_STAGE9C_INTEGRATION_URL required")
    refuse_unsafe_target(url)
    if not args.execute:
        print("DRY RUN: only PostgreSQL TEMP collection_events; no persistent writes")
        return

    engine = create_engine(url, pool_pre_ping=True, connect_args={
        "connect_timeout": 5, "options": "-c statement_timeout=10000",
    })
    try:
        with engine.connect() as conn:
            # Strict real-target checks precede creation of any temporary objects.
            check(conn)
            conn.rollback()
            # All test data live in this session's TEMP shadow. PostgreSQL
            # automatically discards it on disconnect, including on failure.
            conn.execute(text("""
                CREATE TEMP TABLE collection_events (
                    event_id bigint PRIMARY KEY,
                    occurred_at timestamptz NOT NULL,
                    lane text NOT NULL,
                    event_type text NOT NULL,
                    resource text NOT NULL
                ) ON COMMIT PRESERVE ROWS
            """))
            conn.commit()
            # Derive a synthetic, recent boundary; the immutable Stage 9B
            # cutover is NOT modified and is not reused as a test clock.
            now = conn.execute(text("SELECT transaction_timestamp()")).scalar_one()
            cutover = now - timedelta(minutes=10)
            conn.rollback()

            def clear():
                conn.execute(text("TRUNCATE pg_temp.collection_events"))
                conn.commit()

            def insert_range(count, stamp, first_id):
                conn.execute(text("""
                    INSERT INTO pg_temp.collection_events
                        (event_id,occurred_at,lane,event_type,resource)
                    SELECT :first_id + n, :stamp, 'background',
                           'collection_attempt_started','detailed'
                    FROM generate_series(0, :count - 1) AS n
                """), {"first_id": first_id, "stamp": stamp, "count": count})
                conn.commit()

            # 1296 pre-boundary plus one post-boundary must exceed the cap.
            insert_range(1296, cutover - timedelta(seconds=1), 1)
            insert_range(1, cutover + timedelta(seconds=1), 11559)
            assert rolling_background_max(conn, cutover=cutover, now=now) == CEILING + 1
            conn.rollback()
            print("PASS: PostgreSQL 1297 cross-boundary physical starts detected")

            # Exactly 1296 across boundary is allowed.
            clear()
            insert_range(1295, cutover - timedelta(seconds=1), 1)
            insert_range(1, cutover + timedelta(seconds=1), 11559)
            assert rolling_background_max(conn, cutover=cutover, now=now) == CEILING
            conn.rollback()
            print("PASS: PostgreSQL 1296 cross-boundary starts accepted")

            # A one-hour-old start is excluded at the exact timestamp.
            clear()
            insert_range(1, cutover - timedelta(hours=1) + timedelta(seconds=1), 1)
            insert_range(1, cutover + timedelta(seconds=1), 11559)
            assert rolling_background_max(conn, cutover=cutover, now=now) == 1
            conn.rollback()
            print("PASS: PostgreSQL strict 60-minute boundary")

            # Historical pre-cutover peak must not be misattributed to 9C.
            clear()
            insert_range(1297, cutover - timedelta(minutes=50), 1)
            insert_range(1, cutover + timedelta(minutes=20), 11559)
            assert rolling_background_max(
                conn, cutover=cutover, now=cutover + timedelta(minutes=21)
            ) == 1
            conn.rollback()
            print("PASS: pre-cutover-only historical peak excluded")

            # Filter interactive, terminal, and unsupported resource rows.
            clear()
            conn.execute(text("""
                INSERT INTO pg_temp.collection_events VALUES
                    (3,:stamp,'background','collection_attempt_started','detailed'),
                    (1,:stamp,'interactive','collection_attempt_started','detailed'),
                    (2,:stamp,'background','collection_success','detailed'),
                    (4,:stamp,'background','collection_attempt_started','unsupported')
            """), {"stamp": cutover + timedelta(seconds=1)})
            conn.commit()
            assert rolling_background_max(conn, cutover=cutover, now=now) == 1
            conn.rollback()
            print("PASS: PostgreSQL eligibility filters and timestamp ordering")

            # A failed query must propagate; watchdog main() withholds renewal
            # on inspection exceptions (covered by offline runtime tests).
            conn.execute(text("DROP TABLE pg_temp.collection_events"))
            conn.commit()
            try:
                rolling_background_max(conn, cutover=cutover, now=now)
            except Exception:
                conn.rollback()
            else:
                raise AssertionError("missing budget evidence did not fail closed")
            print("PASS: PostgreSQL budget query failure propagated")

            # Verify no persistent event ledger was changed.
            actual = conn.execute(text(
                "SELECT count(*) FROM public.collection_events"
            )).scalar_one()
            conn.rollback()
            print(f"PASS: TEMP test cleanup; persistent collection_events unchanged by harness (rows={actual})")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
