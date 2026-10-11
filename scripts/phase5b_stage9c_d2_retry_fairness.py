"""Guarded D2 real-SQL retry precedence and eligibility proof, no HTTP."""
from __future__ import annotations

import argparse
import os
from uuid import uuid4

from sqlalchemy import create_engine, text

from bf4ps.collection_jobs import claim_next_job, enqueue_job
from bf4ps.distributed_retry_metrics import RETRY_FAIRNESS_SQL
from scripts.phase5b_stage9c_d2_ledger_integration import (
    EXPECTED_DB, EXPECTED_IP, EXPECTED_USER, HEAD, validate_target,
)


def run(url: str) -> None:
    validate_target(url)
    engine = create_engine(url, connect_args={"connect_timeout": 5})
    marker = "synthetic-fairness-" + uuid4().hex
    collector = uuid4()
    soldiers = []
    try:
        with engine.connect() as conn:
            identity = conn.execute(text(
                "SELECT current_database(),current_user,inet_server_addr(),"
                "pg_is_in_recovery(),current_setting('transaction_read_only')"
            )).one()
            if (identity[0], identity[1], str(identity[2]), identity[3], identity[4]) != (
                EXPECTED_DB, EXPECTED_USER, EXPECTED_IP, False, "off"
            ):
                raise RuntimeError("REFUSING unexpected D2 identity")
            if conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() != HEAD:
                raise RuntimeError("REFUSING unexpected migration head")
            if any(conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
                   for table in ("soldiers", "collection_jobs", "collectors")):
                raise RuntimeError("REFUSING nonempty D2 core tables")
            conn.rollback()

        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO collectors (collector_uuid,collector_name,hostname,lane,egress_key)
                VALUES (:uuid,:name,'tcou','background',:name)
            """), {"uuid": collector, "name": marker})
            for index in range(5):
                sid = conn.execute(text("""
                    INSERT INTO soldiers
                        (persona_id,platform,current_name,first_seen_at,last_seen_at)
                    VALUES (:persona,'pc',:name,clock_timestamp(),clock_timestamp())
                    RETURNING soldier_id
                """), {"persona": 1_700_000_000 + uuid4().int % 100_000_000,
                       "name": marker + str(index)}).scalar_one()
                soldiers.append(sid)
                enqueue_job(conn, soldier_id=sid, resource="detailed",
                            lane="background", priority_class="bootstrap", reason=marker)

            # Deliberately give the retry a higher priority_value than fresh jobs.
            conn.execute(text("""
                UPDATE collection_jobs
                SET last_error_at=clock_timestamp()-interval '2 hours',
                    priority_value=999, eligible_at=clock_timestamp()-interval '31 minutes'
                WHERE soldier_id=:sid
            """), {"sid": soldiers[0]})
            # A deferred retry must never be claimed before its cooldown ends.
            conn.execute(text("""
                UPDATE collection_jobs
                SET last_error_at=clock_timestamp(), priority_value=9999,
                    eligible_at=clock_timestamp()+interval '1 hour'
                WHERE soldier_id=:sid
            """), {"sid": soldiers[1]})
            # Eligible for only 29 minutes: still behind fresh jobs, even
            # though the failure itself happened hours ago.
            conn.execute(text("""
                UPDATE collection_jobs
                SET last_error_at=clock_timestamp()-interval '3 hours',
                    priority_value=99999, eligible_at=clock_timestamp()-interval '29 minutes'
                WHERE soldier_id=:sid
            """), {"sid": soldiers[2]})
            now = conn.execute(text("SELECT clock_timestamp()")).scalar_one()
            rows = conn.execute(RETRY_FAIRNESS_SQL, {"observed_at": now}).mappings().all()
            metric = next((r for r in rows if r["lane"] == "background"
                           and r["resource"] == "detailed"
                           and r["priority_class"] == "bootstrap"), None)
            assert metric is not None, rows
            assert (metric["fresh_eligible"], metric["retries_eligible"],
                    metric["retries_waiting"]) == (2, 2, 1), metric
            assert metric["oldest_retry_wait_seconds"] > 1800, metric

        order = []
        for _ in range(4):
            with engine.begin() as conn:
                claimed = claim_next_job(conn, collector_uuid=collector,
                                         resource="detailed", lane="background",
                                         allowed_soldier_ids=soldiers)
                assert claimed is not None
                order.append(claimed.soldier_id)
        assert order[0] == soldiers[0], order  # aged eligible retry promoted
        assert set(order[1:3]) == set(soldiers[3:]), order  # fresh before young retry
        assert order[3] == soldiers[2], order
        with engine.begin() as conn:
            assert claim_next_job(conn, collector_uuid=collector,
                                  resource="detailed", lane="background",
                                  allowed_soldier_ids=soldiers) is None
        print("PASS: D2 SQL metrics fresh=2 eligible-retry=2 deferred-retry=1")
        print("PASS: 31-minute eligible retry promoted; fresh jobs before 29-minute retry; cooldown respected")
        print("PASS: aged eligible retry outranks continuously replenished fresh work in same class")
    finally:
        try:
            if soldiers:
                with engine.begin() as conn:
                    conn.execute(text("DELETE FROM collection_jobs WHERE soldier_id=ANY(:ids)"),
                                 {"ids": soldiers})
                    conn.execute(text("DELETE FROM soldiers WHERE soldier_id=ANY(:ids)"),
                                 {"ids": soldiers})
                    conn.execute(text("DELETE FROM collectors WHERE collector_uuid=:uuid"),
                                 {"uuid": collector})
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
