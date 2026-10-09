#!/usr/bin/env python3
"""Read-only T4 incomplete-run diagnostic. Never cleans up or changes a lease."""
from __future__ import annotations

import argparse
import os
from uuid import UUID

from sqlalchemy import create_engine, text

from scripts.phase5b_stage9c_postgres_integration import (
    EXPECTED_DATABASE, EXPECTED_IP, EXPECTED_USER, refuse_unsafe_target,
)
from scripts.phase5b_stage9c_t4_barrier import READY, RELEASE, DONE, events

HOSTS = ("tcou", "hnl-01", "kah-01")


def inspect(conn, marker):
    identity = conn.execute(text("""
        SELECT current_database(),current_user,inet_server_addr(),
               pg_is_in_recovery(),current_setting('transaction_read_only'),
               current_setting('transaction_isolation')
    """)).one()
    expected = (EXPECTED_DATABASE, EXPECTED_USER, EXPECTED_IP, False, "on", "repeatable read")
    actual = (identity[0], identity[1], str(identity[2]), identity[3], identity[4], identity[5])
    if actual != expected:
        raise RuntimeError(f"REFUSING unexpected scratch identity/isolation: {actual}")
    if conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() != "0004_stage9c_supervision_runs":
        raise RuntimeError("REFUSING unexpected Alembic revision")
    names = {h: marker + "_" + h for h in HOSTS}
    collectors = conn.execute(text("""
        SELECT collector_uuid, collector_name, hostname, drained, heartbeat_state
        FROM collectors WHERE collector_name IN (:a,:b,:c)
        ORDER BY hostname
    """), {"a": names["tcou"], "b": names["hnl-01"], "c": names["kah-01"]}).all()
    soldiers = conn.execute(text("""
        SELECT soldier_id, current_name FROM soldiers
        WHERE current_name IN (:a,:b,:c) ORDER BY soldier_id
    """), {"a": names["tcou"], "b": names["hnl-01"], "c": names["kah-01"]}).all()
    jobs = conn.execute(text("""
        SELECT job_id,soldier_id,status,attempt_count,collector_uuid,
               claimed_at,started_at,lease_expires_at,
               CASE WHEN lease_expires_at IS NULL THEN NULL
                    ELSE lease_expires_at <= now() END AS lease_expired
        FROM collection_jobs WHERE reason=:marker ORDER BY job_id
    """), {"marker": marker}).all()
    counts = conn.execute(text("""
        SELECT event_type, COUNT(*) AS n, MIN(occurred_at) AS oldest,
               MAX(occurred_at) AS newest
        FROM collection_events
        WHERE metadata->>'stage9c_t4_marker'=:marker
        GROUP BY event_type ORDER BY event_type
    """), {"marker": marker}).all()
    for label, data in (("COLLECTORS", collectors), ("SOLDIERS", soldiers),
                        ("JOBS", jobs), ("EVENT_COUNTS", counts)):
        print(label, len(data))
        for item in data:
            print(" ", item)
    for kind in (READY, RELEASE, DONE):
        ledger = events(conn, marker, kind)
        print("LEDGER", kind, [(r.host, r.outcome) for r in ledger])
    print("DIAGNOSTIC ONLY: do not infer participants have exited or cleanup is authorized")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    marker = "stage9c_t4_" + str(UUID(args.run_id))
    url = os.environ.get("BF4PS_STAGE9C_INTEGRATION_URL", "")
    refuse_unsafe_target(url)
    engine = create_engine(url, pool_pre_ping=True, connect_args={
        "connect_timeout": 5, "options": "-c statement_timeout=15000",
    })
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            try:
                inspect(conn, marker)
            finally:
                conn.rollback()
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
