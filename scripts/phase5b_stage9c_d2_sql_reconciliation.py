"""D2 PostgreSQL SQL-vs-model validation using transaction-local TEMP fixtures.

No writes to persistent tables. The real schema is checked, then TEMP tables
shadow the three source tables for the duration of one rolled-back transaction.
No HTTP, no collector activation, no T4 access.
"""
from __future__ import annotations

import argparse
import os
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import create_engine, inspect, text

from bf4ps.dispatch_budget_conservative import ReconciliationEvidence, conservative_background_usage
from bf4ps.dispatch_budget_sql import read_conservative_background_usage
from scripts.phase5b_stage9c_d2_ledger_integration import (
    EXPECTED_DB, EXPECTED_IP, EXPECTED_USER, HEAD, validate_target,
)

TEMP_DDL = (
    "CREATE TEMP TABLE collection_events (job_id bigint, attempt_number integer, "
    "resource text, lease_token uuid, occurred_at timestamptz, lane text, event_type text) ON COMMIT DROP",
    "CREATE TEMP TABLE collection_jobs (job_id bigint, attempt_count integer, "
    "resource text, lease_token uuid, claimed_at timestamptz, "
    "lease_expires_at timestamptz, lane text, status text) ON COMMIT DROP",
    "CREATE TEMP TABLE outbound_dispatches (job_id bigint, attempt_number integer, "
    "resource text, lease_token uuid, admitted_at timestamptz, lane text) ON COMMIT DROP",
)


def run(url: str) -> None:
    validate_target(url)
    engine = create_engine(url, connect_args={"connect_timeout": 5})
    try:
        with engine.connect() as conn:
            actual = conn.execute(text(
                "SELECT current_database(),current_user,inet_server_addr(),"
                "pg_is_in_recovery(),current_setting('transaction_read_only')"
            )).one()
            if (actual[0], actual[1], str(actual[2]), actual[3], actual[4]) != (
                EXPECTED_DB, EXPECTED_USER, EXPECTED_IP, False, "off"
            ):
                raise RuntimeError("REFUSING unexpected database identity")
            if conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() != HEAD:
                raise RuntimeError("REFUSING unexpected migration revision")
            required = {
                "collection_events": {"job_id", "attempt_number", "resource", "lease_token", "occurred_at", "lane", "event_type"},
                "collection_jobs": {"job_id", "attempt_count", "resource", "lease_token", "claimed_at", "lease_expires_at", "lane", "status"},
                "outbound_dispatches": {"job_id", "attempt_number", "resource", "lease_token", "admitted_at", "lane"},
            }
            for table, columns in required.items():
                found = {column["name"] for column in inspect(conn).get_columns(table, schema="public")}
                if not columns <= found:
                    raise RuntimeError(f"REFUSING schema mismatch: {table}")
            # End introspection transaction before opening fixture transaction.
            conn.rollback()
            with conn.begin():
                conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('bf4ps:phase5b-background-service'))"))
                at = conn.execute(text("SELECT clock_timestamp()")).scalar_one()
                for ddl in TEMP_DDL:
                    conn.execute(text(ddl))
                token = uuid4()
                other_token = uuid4()
                scenarios = [
                    ("empty", []),
                    ("three-source-match", [
                        ("started", 101, 1, token, at, None),
                        ("reserved", 101, 1, token, at, at + timedelta(minutes=2)),
                        ("dispatch", 101, 1, token, at, None),
                    ]),
                    ("null-event-and-duplicate-start", [
                        ("started", 101, 1, None, at, None),
                        ("started", 101, 1, token, at, None),
                        ("started", 101, 1, token, at, None),
                        ("dispatch", 101, 1, token, at, None),
                    ]),
                    ("reclaim-and-expiry", [
                        ("reserved", 101, 1, other_token, at, at + timedelta(minutes=1)),
                        ("dispatch", 101, 1, token, at - timedelta(hours=1), None),
                        ("started", 102, 1, token, at - timedelta(minutes=2), None),
                    ]),
                ]
                for name, entries in scenarios:
                    for table in ("collection_events", "collection_jobs", "outbound_dispatches"):
                        conn.execute(text(f"DELETE FROM pg_temp.{table}"))
                    evidence = []
                    for source, job, attempt, lease, stamp, expiry in entries:
                        if source == "started":
                            conn.execute(text(
                                "INSERT INTO pg_temp.collection_events VALUES "
                                "(:job,:attempt,'weapons',:lease,:stamp,'background','collection_attempt_started')"
                            ), dict(job=job, attempt=attempt, lease=lease, stamp=stamp))
                        elif source == "reserved":
                            conn.execute(text(
                                "INSERT INTO pg_temp.collection_jobs VALUES "
                                "(:job,:attempt,'weapons',:lease,:stamp,:expiry,'background','claimed')"
                            ), dict(job=job, attempt=attempt, lease=lease, stamp=stamp, expiry=expiry))
                        else:
                            conn.execute(text(
                                "INSERT INTO pg_temp.outbound_dispatches VALUES "
                                "(:job,:attempt,'weapons',:lease,:stamp,'background')"
                            ), dict(job=job, attempt=attempt, lease=lease, stamp=stamp))
                        evidence.append(ReconciliationEvidence(
                            source, job, attempt, "weapons", str(lease) if lease else None, stamp, expiry
                        ))
                    expected = conservative_background_usage(evidence, at=at)
                    observed = read_conservative_background_usage(conn, at=at)
                    if observed != expected:
                        raise AssertionError(f"{name}: SQL={observed}, model={expected}")
                    print(f"PASS: {name} SQL={observed} model={expected}")
                # Temp tables disappear at transaction end. No persistent writes.
            print("PASS: D2 three-source SQL/model parity, TEMP fixtures only, no persistent writes")
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
