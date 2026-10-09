#!/usr/bin/env python3
"""Dedicated scratch PostgreSQL integration of Stage 9C read-only checkpoint.

Uses only allowlisted scratch target, a disposable supervision row, and
session-local TEMP collection_events. No collectors, migrations or HTTP.
"""
import argparse
import os
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import create_engine, text

from bf4ps.stage9c_checkpoint_audit import inspect_checkpoint
from scripts.phase5b_stage9c_abort_drain_scratch import check, create_run
from scripts.phase5b_stage9c_postgres_integration import refuse_unsafe_target


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    url = os.environ.get("BF4PS_STAGE9C_INTEGRATION_URL", "")
    if not url:
        parser.error("BF4PS_STAGE9C_INTEGRATION_URL required")
    refuse_unsafe_target(url)
    if not args.execute:
        print("DRY RUN: no PostgreSQL changes")
        return
    engine = create_engine(url, pool_pre_ping=True, connect_args={
        "connect_timeout": 5,
        "options": "-c statement_timeout=10000 -c lock_timeout=1000",
    })
    run_id = uuid4()
    created = False
    try:
        with engine.connect() as conn:
            check(conn)
            conn.rollback()
            # This scratch fixture creates a disposable row before switching
            # to a read-only transaction; the audited function never writes.
            create_run(conn, run_id, uuid4())
            conn.commit()
            created = True
            conn.execute(text("""
                CREATE TEMP TABLE collection_events (
                    event_id bigint PRIMARY KEY,
                    occurred_at timestamptz NOT NULL,
                    event_type text NOT NULL,
                    lane text,
                    resource text
                ) ON COMMIT PRESERVE ROWS
            """))
            conn.commit()
            now = conn.execute(text("SELECT transaction_timestamp()")).scalar_one()
            conn.rollback()
            start = now - timedelta(minutes=10)
            conn.execute(text("""
                UPDATE stage9c_supervision_runs
                SET started_at=:start,deadline_at=:deadline
                WHERE run_id=:id
            """), {"start": start, "deadline": start + timedelta(hours=6), "id": run_id})
            conn.commit()
            conn.execute(text("""
                INSERT INTO pg_temp.collection_events
                (event_id,occurred_at,event_type,lane,resource)
                SELECT n,:stamp,'collection_attempt_started','background','detailed'
                FROM generate_series(1,1296) n
            """), {"stamp": start - timedelta(minutes=1)})
            conn.execute(text("""
                INSERT INTO pg_temp.collection_events
                VALUES (1297,:stamp,'collection_attempt_started','background','detailed')
            """), {"stamp": start + timedelta(minutes=1)})
            conn.commit()

            def audit_readonly():
                conn.exec_driver_sql("SET TRANSACTION READ ONLY")
                try:
                    result = inspect_checkpoint(
                        conn, run_id, expected_database="bf4ps_scratch_stage9c_integration"
                    )
                    # Explicitly prove the transaction refuses mutation.
                    try:
                        conn.execute(text("DELETE FROM stage9c_supervision_runs WHERE run_id=:id"),
                                     {"id": run_id})
                    except Exception:
                        conn.rollback()
                    else:
                        raise AssertionError("READ ONLY transaction unexpectedly allowed DELETE")
                    return result
                finally:
                    conn.rollback()

            result = audit_readonly()
            assert result["rolling_max"] == 1297
            assert result["observed_budget_pass"] is False
            assert result["ledger_completeness_verified"] is False
            print("PASS: scratch read-only checkpoint detects cross-supervision 1297 starts")

            conn.execute(text("DELETE FROM pg_temp.collection_events WHERE event_id=1297"))
            conn.commit()
            result = audit_readonly()
            assert result["rolling_max"] == 1296
            assert result["observed_budget_pass"] is True
            assert result["ledger_completeness_verified"] is False
            print("PASS: 1296 observed starts; completeness remains UNVERIFIED")
            print("PASS: PostgreSQL READ ONLY transaction blocks attempted mutation")
    finally:
        if created:
            with engine.begin() as conn:
                conn.execute(text("DELETE FROM stage9c_supervision_runs WHERE run_id=:id"),
                             {"id": run_id})
        engine.dispose()


if __name__ == "__main__":
    main()
