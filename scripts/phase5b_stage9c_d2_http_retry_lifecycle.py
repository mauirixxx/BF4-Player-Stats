"""Guarded D2 real PostgreSQL 403/429 retry lifecycle, no HTTP."""
from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import create_engine, text

from bf4ps.collection_jobs import claim_next_job, enqueue_job, mark_job_running
from bf4ps.battlelog_detailed import DetailedStatsHTTPError
from bf4ps.battlelog_weapons import WeaponStatsHTTPError
from bf4ps.battlelog_vehicles import VehicleStatsHTTPError
from bf4ps.detailed_failure import classify_detailed_failure, persist_detailed_retry_failure
from bf4ps.weapon_failure import classify_weapon_failure, persist_weapon_retry_failure
from bf4ps.vehicle_failure import classify_vehicle_failure, persist_vehicle_retry_failure
from scripts.phase5b_stage9c_d2_ledger_integration import (
    EXPECTED_DB, EXPECTED_IP, EXPECTED_USER, HEAD, validate_target,
)

CASES = (
    ("detailed", DetailedStatsHTTPError, classify_detailed_failure, persist_detailed_retry_failure),
    ("weapons", WeaponStatsHTTPError, classify_weapon_failure, persist_weapon_retry_failure),
    ("vehicles", VehicleStatsHTTPError, classify_vehicle_failure, persist_vehicle_retry_failure),
)


def run(url: str) -> None:
    validate_target(url)
    engine = create_engine(url, connect_args={"connect_timeout": 5})
    marker = "synthetic-retry-lifecycle-" + uuid4().hex
    collector = uuid4()
    soldier_id = None
    try:
        with engine.connect() as conn:
            row = conn.execute(text(
                "SELECT current_database(),current_user,inet_server_addr(),"
                "pg_is_in_recovery(),current_setting('transaction_read_only')"
            )).one()
            if (row[0], row[1], str(row[2]), row[3], row[4]) != (
                EXPECTED_DB, EXPECTED_USER, EXPECTED_IP, False, "off"
            ):
                raise RuntimeError("REFUSING unexpected D2 identity")
            if conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() != HEAD:
                raise RuntimeError("REFUSING unexpected migration head")
            if any(conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
                   for table in ("soldiers", "collection_jobs", "collectors", "collection_events")):
                raise RuntimeError("REFUSING nonempty D2 core tables")
            conn.rollback()

        with engine.begin() as conn:
            soldier_id = conn.execute(text("""
                INSERT INTO soldiers (persona_id,platform,current_name,first_seen_at,last_seen_at)
                VALUES (:persona,'pc',:name,clock_timestamp(),clock_timestamp())
                RETURNING soldier_id
            """), {"persona": 1_600_000_000 + uuid4().int % 100_000_000,
                   "name": marker}).scalar_one()
            conn.execute(text("""
                INSERT INTO collectors (collector_uuid,collector_name,hostname,lane,egress_key)
                VALUES (:uuid,:name,'tcou','background',:name)
            """), {"uuid": collector, "name": marker})
            for resource, _, _, _ in CASES:
                enqueue_job(conn, soldier_id=soldier_id, resource=resource,
                            lane="background", priority_class="bootstrap", reason=marker)

        for resource, error_type, classify, persist in CASES:
            for status in (403, 429):
                with engine.begin() as conn:
                    job = claim_next_job(
                        conn, collector_uuid=collector, resource=resource,
                        lane="background", allowed_soldier_ids=[soldier_id])
                    assert job is not None and mark_job_running(conn, job), (resource, status)
                attempted_at = datetime.now(timezone.utc)
                failure = classify(error_type(status, f"synthetic HTTP {status}"))
                assert failure.error_class == "battlelog_throttle"
                with engine.begin() as conn:
                    persist(
                        conn, job=job, failure=failure, attempted_at=attempted_at,
                        persona_id=1, platform="pc", collector_name=marker,
                        hostname="tcou", egress_key=marker, duration_ms=8,
                        retry_after_seconds=3600,
                    )

                with engine.connect() as conn:
                    row = conn.execute(text("""
                        SELECT status,eligible_at,last_error_class,last_error_at,
                               collector_uuid,lease_token,attempt_count
                        FROM collection_jobs WHERE job_id=:job
                    """), {"job": job.job_id}).one()
                    assert row.status == "pending" and row.last_error_class == "battlelog_throttle"
                    assert row.collector_uuid is None and row.lease_token is None
                    assert row.attempt_count == job.attempt_count
                    assert abs((row.eligible_at - attempted_at).total_seconds() - 3600) < 1
                    event = conn.execute(text("""
                        SELECT http_status,error_class,result,metadata
                        FROM collection_events
                        WHERE job_id=:job AND attempt_number=:attempt
                          AND event_type='collection_failure'
                    """), {"job": job.job_id, "attempt": job.attempt_count}).one()
                    assert (event.http_status, event.error_class, event.result) == (
                        status, "battlelog_throttle", "temporary_failure")
                    assert int(event.metadata["retry_after_seconds"]) == 3600
                    state = conn.execute(text("""
                        SELECT * FROM collection_state WHERE soldier_id=:sid
                    """), {"sid": soldier_id}).mappings().one()
                    assert state[f"{resource}_state"] == "temporary_failure"
                    conn.rollback()

                with engine.begin() as conn:
                    assert claim_next_job(
                        conn, collector_uuid=collector, resource=resource,
                        lane="background", allowed_soldier_ids=[soldier_id]) is None
                    # Time travel only the synthetic queue eligibility; no clock changes.
                    conn.execute(text("""
                        UPDATE collection_jobs SET eligible_at=clock_timestamp()-interval '1 second'
                        WHERE job_id=:job
                    """), {"job": job.job_id})
                if status == 403:
                    # Reclaim to exercise the next 429 attempt.
                    with engine.begin() as conn:
                        reclaimed = claim_next_job(
                            conn, collector_uuid=collector, resource=resource,
                            lane="background", allowed_soldier_ids=[soldier_id])
                        assert reclaimed and reclaimed.attempt_count == job.attempt_count + 1
                        # Return it to pending so next loop can claim normally.
                        conn.execute(text("""
                            UPDATE collection_jobs SET status='pending',collector_uuid=NULL,
                                lease_token=NULL,claimed_at=NULL,started_at=NULL,
                                lease_expires_at=NULL WHERE job_id=:job
                        """), {"job": job.job_id})
                else:
                    with engine.begin() as conn:
                        reclaimed = claim_next_job(
                            conn, collector_uuid=collector, resource=resource,
                            lane="background", allowed_soldier_ids=[soldier_id])
                        assert reclaimed and reclaimed.attempt_count == job.attempt_count + 1
                print(f"PASS: D2 {resource} HTTP {status} event/cooldown/reclaim")
        with engine.connect() as conn:
            total = conn.execute(text("""
                SELECT count(*) FROM collection_events WHERE soldier_id=:sid
                  AND event_type='collection_failure'
            """), {"sid": soldier_id}).scalar_one()
            assert total == 6, total
            conn.rollback()
    finally:
        try:
            if soldier_id is not None:
                with engine.begin() as conn:
                    conn.execute(text("DELETE FROM collection_events WHERE soldier_id=:sid"), {"sid": soldier_id})
                    conn.execute(text("DELETE FROM collection_jobs WHERE soldier_id=:sid"), {"sid": soldier_id})
                    conn.execute(text("DELETE FROM collection_state WHERE soldier_id=:sid"), {"sid": soldier_id})
                    conn.execute(text("DELETE FROM soldiers WHERE soldier_id=:sid AND current_name=:name"),
                                 {"sid": soldier_id, "name": marker})
                    conn.execute(text("DELETE FROM collectors WHERE collector_uuid=:uuid"), {"uuid": collector})
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
