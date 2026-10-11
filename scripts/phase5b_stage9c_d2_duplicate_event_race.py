"""Guarded D2-only PostgreSQL duplicate audit concurrency check; no HTTP.

Two independent connections race to record the SAME discarded fetch against
one committed synthetic winner. No production tables or T4 scratch touched.
"""
from __future__ import annotations

import argparse
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

from sqlalchemy import create_engine, text

from bf4ps.collection_jobs import ClaimedJob
from bf4ps.distributed_duplicate_events import record_discarded_duplicate
from scripts.phase5b_stage9c_d2_ledger_integration import (
    EXPECTED_DB, EXPECTED_IP, EXPECTED_USER, HEAD, validate_target,
)


def run(url: str) -> None:
    validate_target(url)
    engine = create_engine(url, pool_size=3, max_overflow=0, connect_args={"connect_timeout": 5})
    marker = "synthetic-duplicate-" + uuid4().hex
    soldier_id = None
    job_id = 1_500_000_000 + (uuid4().int % 100_000_000)
    lease = uuid4()
    job = None
    try:
        with engine.connect() as conn:
            row = conn.execute(text(
                "SELECT current_database(),current_user,inet_server_addr(),"
                "pg_is_in_recovery(),current_setting('transaction_read_only')"
            )).one()
            if (row[0], row[1], str(row[2]), row[3], row[4]) != (
                EXPECTED_DB, EXPECTED_USER, EXPECTED_IP, False, "off"
            ):
                raise RuntimeError("REFUSING unexpected D2 connection")
            if conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() != HEAD:
                raise RuntimeError("REFUSING unexpected D2 migration head")
            if any(conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
                   for table in ("soldiers", "collection_events", "collection_jobs")):
                raise RuntimeError("REFUSING nonempty D2 core tables")
            conn.rollback()

        with engine.begin() as conn:
            soldier_id = conn.execute(text("""
                INSERT INTO soldiers
                    (persona_id,platform,current_name,first_seen_at,last_seen_at)
                VALUES (:persona,'pc',:name,clock_timestamp(),clock_timestamp())
                RETURNING soldier_id
            """), {"persona": 1_900_000_000 + (uuid4().int % 100_000_000),
                   "name": marker}).scalar_one()
            conn.execute(text("""
                INSERT INTO collection_events
                    (job_id,soldier_id,persona_id,platform,resource,lane,
                     event_type,attempt_number,result,metadata)
                VALUES (:job_id,:soldier_id,1,'pc','detailed','background',
                        'collection_success',2,'success',
                        jsonb_build_object('synthetic_marker',CAST(:marker AS text)))
            """), {"job_id": job_id, "soldier_id": soldier_id, "marker": marker})
        job = ClaimedJob(job_id, soldier_id, "detailed", "background", 1, uuid4(), lease)
        barrier = Barrier(2)

        def loser() -> bool:
            barrier.wait(timeout=15)
            with engine.begin() as conn:
                return record_discarded_duplicate(
                    conn, job=job, persona_id=1, platform="pc",
                    collector_name=marker, hostname="tcou-scratch",
                    egress_key="synthetic-no-http", duration_ms=10, http_status=200,
                )

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(loser) for _ in range(2)]
            outcomes = [f.result(timeout=20) for f in futures]
        if sorted(outcomes) != [True, True]:
            raise AssertionError(f"expected both handled with one audit insertion: {outcomes}")
        with engine.connect() as conn:
            count = conn.execute(text("""
                SELECT count(*) FROM collection_events
                WHERE event_type='collection_duplicate_discarded'
                  AND metadata->>'original_job_id'=:job_id
                  AND metadata->>'original_lease_token'=:lease
            """), {"job_id": str(job_id), "lease": str(lease)}).scalar_one()
            conn.rollback()
        if count != 1:
            raise AssertionError(f"expected one duplicate audit event; got {count}")
        print("PASS: D2 two independent connections, one duplicate audit insert, one suppressed")
        print("LIMIT: synthetic committed winner; does not test collector HTTP or persistence winner race")
    finally:
        try:
            if soldier_id is not None:
                with engine.begin() as conn:
                    conn.execute(text("""
                        DELETE FROM collection_events
                        WHERE (job_id=:job_id AND soldier_id=:soldier_id)
                           OR (event_type='collection_duplicate_discarded'
                               AND metadata->>'original_job_id'=:job_id_text
                               AND metadata->>'original_lease_token'=:lease)
                    """), {"job_id": job_id, "soldier_id": soldier_id,
                           "job_id_text": str(job_id), "lease": str(lease)})
                    conn.execute(text("DELETE FROM soldiers WHERE soldier_id=:soldier_id AND current_name=:marker"),
                                 {"soldier_id": soldier_id, "marker": marker})
        finally:
            engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        parser.error("--execute is required")
    url = os.environ.get("BF4PS_STAGE9C_D2_URL")
    if not url:
        parser.error("BF4PS_STAGE9C_D2_URL is required")
    run(url)
