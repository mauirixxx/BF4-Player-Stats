"""D2-only real PostgreSQL persistence-failure audit proof for all collectors.

No HTTP, production writes, migrations, or queue execution. Synthetic
unconfirmed lease-loss exceptions are passed through each collector's actual
failure-audit function and the committed events are verified.
"""
from __future__ import annotations

import argparse
import os
from uuid import uuid4

from sqlalchemy import create_engine, text

from bf4ps.collection_jobs import ClaimedJob
from bf4ps import detailed_collector, weapon_collector, vehicle_collector
from scripts.phase5b_stage9c_d2_ledger_integration import (
    EXPECTED_DB, EXPECTED_IP, EXPECTED_USER, HEAD, validate_target,
)


def run(url: str) -> None:
    validate_target(url)
    engine = create_engine(url, connect_args={"connect_timeout": 5})
    marker = "synthetic-failure-audit-" + uuid4().hex
    soldier_id = None
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
                   for table in ("soldiers", "collection_events", "collection_jobs", "collectors")):
                raise RuntimeError("REFUSING nonempty D2 core tables")
            conn.rollback()

        with engine.begin() as conn:
            soldier_id = conn.execute(text("""
                INSERT INTO soldiers
                    (persona_id,platform,current_name,first_seen_at,last_seen_at)
                VALUES (:persona,'pc',:name,clock_timestamp(),clock_timestamp())
                RETURNING soldier_id
            """), {"persona": 1_600_000_000 + uuid4().int % 100_000_000,
                   "name": marker}).scalar_one()

        modules = (
            ("detailed", detailed_collector, "_record_detailed_persistence_failure"),
            ("weapons", weapon_collector, "_record_persistence_failure"),
            ("vehicles", vehicle_collector, "_record_vehicle_persistence_failure"),
        )
        for index, (resource, module, fn_name) in enumerate(modules):
            collector_uuid = uuid4()
            job = ClaimedJob(1_500_000_000 + index, soldier_id, resource,
                             "background", 1, collector_uuid, uuid4())
            identity = module.CollectorIdentity(
                collector_uuid=collector_uuid, collector_name=marker,
                hostname="tcou", egress_key="synthetic-no-http")
            kwargs = dict(job=job, identity=identity, persona_id=1, platform="pc",
                          duration_ms=7, exc=RuntimeError(
                              "synthetic lease loss without confirmed competing winner"))
            if resource != "detailed":
                kwargs["response_bytes"] = 123
            getattr(module, fn_name)(engine, **kwargs)

        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT resource,event_type,result,error_class,error_message
                FROM collection_events
                WHERE soldier_id=:sid
                ORDER BY event_id
            """), {"sid": soldier_id}).mappings().all()
            conn.rollback()
        assert len(rows) == 3, rows
        assert [r["resource"] for r in rows] == ["detailed", "weapons", "vehicles"], rows
        assert all(r["event_type"] == "collection_persistence_failure"
                   and r["result"] == "persistence_failure"
                   and "synthetic lease loss" in r["error_message"] for r in rows), rows
        print("PASS: D2 detailed/weapons/vehicles each committed one persistence-failure audit")
        print("LIMIT: tests actual audit functions, not complete collector dispatch/error pipeline")
    finally:
        try:
            if soldier_id is not None:
                with engine.begin() as conn:
                    conn.execute(text("DELETE FROM collection_events WHERE soldier_id=:sid"),
                                 {"sid": soldier_id})
                    conn.execute(text("DELETE FROM soldiers WHERE soldier_id=:sid AND current_name=:name"),
                                 {"sid": soldier_id, "name": marker})
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
