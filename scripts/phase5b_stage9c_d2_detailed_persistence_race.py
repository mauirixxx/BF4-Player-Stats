"""D2-only real detailed persistence winner/loser lease race, no HTTP."""
from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import create_engine, text

from bf4ps.battlelog_detailed import DECIMAL_FIELDS, INTEGER_FIELDS
from bf4ps.collection_jobs import claim_next_job, enqueue_job, mark_job_running
from bf4ps.detailed_persistence import persist_detailed_success
from bf4ps.distributed_duplicate_events import record_discarded_duplicate
from scripts.phase5b_stage9c_d2_ledger_integration import (
    EXPECTED_DB, EXPECTED_IP, EXPECTED_USER, HEAD, validate_target,
)


def run(url: str) -> None:
    validate_target(url)
    engine = create_engine(url, connect_args={"connect_timeout": 5})
    marker = "synthetic-persistence-race-" + uuid4().hex
    collectors = [uuid4(), uuid4()]
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
                raise RuntimeError("REFUSING unexpected D2 database identity")
            if conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() != HEAD:
                raise RuntimeError("REFUSING unexpected migration")
            if any(conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
                   for table in ("soldiers", "collection_events", "collection_jobs", "collectors")):
                raise RuntimeError("REFUSING nonempty D2 core tables")
            conn.rollback()

        with engine.begin() as conn:
            soldier_id = conn.execute(text("""
                INSERT INTO soldiers (persona_id,platform,current_name,first_seen_at,last_seen_at)
                VALUES (:persona,'pc',:name,clock_timestamp(),clock_timestamp())
                RETURNING soldier_id
            """), {"persona": 1_800_000_000 + uuid4().int % 100_000_000,
                   "name": marker}).scalar_one()
            for idx, uid in enumerate(collectors):
                conn.execute(text("""
                    INSERT INTO collectors (collector_uuid,collector_name,hostname,lane,egress_key)
                    VALUES (:uuid,:name,'tcou','background',:egress)
                """), {"uuid": uid, "name": marker + str(idx), "egress": marker + str(idx)})
            job_id = enqueue_job(conn, soldier_id=soldier_id, resource="detailed",
                                 lane="background", priority_class="bootstrap", reason=marker)

        with engine.begin() as conn:
            loser = claim_next_job(conn, collector_uuid=collectors[0],
                                   resource="detailed", lane="background", lease_seconds=120)
            assert loser and loser.job_id == job_id and mark_job_running(conn, loser)
            # Deliberately expire the first lease; the second collector reclaims.
            conn.execute(text("""
                UPDATE collection_jobs SET lease_expires_at=clock_timestamp()-interval '1 second'
                WHERE job_id=:job_id
            """), {"job_id": job_id})
        with engine.begin() as conn:
            winner = claim_next_job(conn, collector_uuid=collectors[1],
                                    resource="detailed", lane="background", lease_seconds=120)
            assert winner and winner.job_id == job_id and mark_job_running(conn, winner)

        stats = {field: i + 1 for i, field in enumerate(INTEGER_FIELDS)}
        from decimal import Decimal
        stats.update({field: Decimal(i + 1) / 10 for i, field in enumerate(DECIMAL_FIELDS)})
        with engine.begin() as conn:
            assert persist_detailed_success(
                conn, job=winner, stats=stats, source_fetched_at=datetime.now(timezone.utc),
                persona_id=1, platform="pc", collector_name=marker + "1",
                hostname="tcou", egress_key=marker + "1", duration_ms=5,
            )

        try:
            with engine.begin() as conn:
                persist_detailed_success(
                    conn, job=loser, stats=stats, source_fetched_at=datetime.now(timezone.utc),
                    persona_id=1, platform="pc", collector_name=marker + "0",
                    hostname="tcou", egress_key=marker + "0", duration_ms=5,
                )
        except RuntimeError as exc:
            if str(exc) != "detailed success rejected: job lease is no longer owned":
                raise
        else:
            raise AssertionError("stale collector incorrectly persisted")

        with engine.begin() as conn:
            assert record_discarded_duplicate(
                conn, job=loser, persona_id=1, platform="pc",
                collector_name=marker + "0", hostname="tcou", egress_key=marker + "0",
                duration_ms=5, http_status=200,
            )
        with engine.connect() as conn:
            counts = [
                conn.execute(text(f"SELECT count(*) FROM {table} WHERE soldier_id=:s"),
                             {"s": soldier_id}).scalar_one()
                for table in ("detailed_stats_current", "detailed_stats_history")
            ]
            success = conn.execute(text("""
                SELECT count(*) FROM collection_events
                WHERE soldier_id=:s AND event_type='collection_success'
            """), {"s": soldier_id}).scalar_one()
            discarded = conn.execute(text("""
                SELECT count(*) FROM collection_events
                WHERE soldier_id=:s AND event_type='collection_duplicate_discarded'
            """), {"s": soldier_id}).scalar_one()
            remaining = conn.execute(text("""
                SELECT count(*) FROM collection_jobs WHERE soldier_id=:s
            """), {"s": soldier_id}).scalar_one()
            conn.rollback()
        assert counts == [1, 1] and success == 1 and discarded == 1 and remaining == 0, (
            counts, success, discarded, remaining
        )
        print("PASS: real detailed persistence winner 1, stale loser rejected, duplicate 1, job 0")
        print("LIMIT: deterministic lease-reclaim interleaving, not simultaneous physical HTTP")
    finally:
        try:
            if soldier_id is not None:
                with engine.begin() as conn:
                    conn.execute(text("DELETE FROM collection_events WHERE soldier_id=:s"),
                                 {"s": soldier_id})
                    conn.execute(text("DELETE FROM soldiers WHERE soldier_id=:s AND current_name=:name"),
                                 {"s": soldier_id, "name": marker})
                    conn.execute(text("DELETE FROM collectors WHERE collector_uuid IN (:a,:b)"),
                                 {"a": collectors[0], "b": collectors[1]})
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
