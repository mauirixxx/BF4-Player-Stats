#!/usr/bin/env python3
"""FI-2: start-event INSERT failure must prevent detailed HTTP (scratch only)."""
from __future__ import annotations

import argparse
import os
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import create_engine, event, text

from bf4ps.background_service import _usage
from bf4ps.detailed_collector import CollectorIdentity, collect_one_detailed_job
from scripts.phase5b_stage9c_abort_drain_scratch import check
from scripts.phase5b_stage9c_postgres_integration import refuse_unsafe_target

TABLES = ("collectors", "soldiers", "collection_jobs", "collection_events", "stage9c_supervision_runs")
MARKER = "stage9c_fi2_start_failure"


def run(url: str) -> None:
    refuse_unsafe_target(url)
    engine = create_engine(url, pool_pre_ping=True, pool_size=3, max_overflow=0,
                           connect_args={"connect_timeout": 5, "options": "-c statement_timeout=15000"})
    marker = str(uuid4())
    uid = uuid4()
    name = f"{MARKER}-{marker}"
    identity = CollectorIdentity(collector_uuid=uid, collector_name=name,
                                 hostname="stage9c-scratch", egress_key=name)
    soldier_id = job_id = None
    preflight = seeded = False
    injected = {"count": 0}
    http_calls = {"count": 0}

    def fail_start_insert(conn, cursor, statement, parameters, context, executemany):
        if ("INSERT INTO collection_events" in statement
                and "'collection_attempt_started'" in statement):
            injected["count"] += 1
            raise RuntimeError("FI-2 injected start-event INSERT failure")

    def forbid_http(*args, **kwargs):
        http_calls["count"] += 1
        raise AssertionError("FI-2 FORBIDDEN external HTTP invocation")

    try:
        with engine.connect() as conn:
            check(conn)
            for table in TABLES:
                if conn.execute(text(f"SELECT count(*) FROM public.{table}")).scalar_one():
                    raise RuntimeError(f"REFUSING nonempty {table}")
            if conn.execute(text("SHOW transaction_isolation")).scalar_one().lower() != "read committed":
                raise RuntimeError("REFUSING non-READ COMMITTED isolation")
            if conn.execute(text("SELECT count(*) FROM public.request_gates WHERE egress_key=:key"),
                            {"key": name}).scalar_one():
                raise RuntimeError("REFUSING preexisting request gate")
            conn.rollback()
        preflight = True
        with engine.begin() as conn:
            conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('bf4ps:stage9c-fi2-fixture'))"))
            for table in TABLES:
                if conn.execute(text(f"SELECT count(*) FROM public.{table}")).scalar_one():
                    raise RuntimeError(f"REFUSING concurrently populated {table}")
            conn.execute(text("""
                INSERT INTO collectors
                    (collector_uuid,collector_name,hostname,lane,egress_key,
                     enabled,drained,heartbeat_state)
                VALUES (:uid,:name,'stage9c-scratch','background',:name,true,false,'healthy')
            """), {"uid": uid, "name": name})
            soldier_id = int(conn.execute(text("""
                INSERT INTO soldiers
                    (persona_id,platform,current_name,first_seen_at,last_seen_at)
                VALUES (:persona,'pc',:name,now(),now()) RETURNING soldier_id
            """), {"persona": 800000000000 + int(uid.int % 10000000), "name": name}).scalar_one())
            job_id = int(conn.execute(text("""
                INSERT INTO collection_jobs
                    (soldier_id,resource,lane,priority_class,reason,
                     status,priority_value,eligible_at)
                VALUES (:sid,'detailed','background','active',:reason,
                        'pending',0,now()) RETURNING job_id
            """), {"sid": soldier_id, "reason": name}).scalar_one())
        seeded = True

        # Only the actual production start-event INSERT is faulted. The SQL
        # never reaches PostgreSQL; engine.begin() must roll back and propagate.
        event.listen(engine, "before_cursor_execute", fail_start_insert)
        try:
            with patch("bf4ps.detailed_collector.fetch_detailed_stats", side_effect=forbid_http):
                try:
                    collect_one_detailed_job(
                        engine, identity=identity, request_interval_seconds=0,
                        allowed_soldier_ids=[soldier_id], enforce_production_budget=True,
                    )
                except RuntimeError as exc:
                    if str(exc) != "FI-2 injected start-event INSERT failure":
                        raise
                else:
                    raise AssertionError("FI-2 start-event failure was swallowed")
        finally:
            event.remove(engine, "before_cursor_execute", fail_start_insert)

        if injected["count"] != 1 or http_calls["count"]:
            raise AssertionError(f"wrong injection/HTTP counts: {injected}, {http_calls}")
        with engine.begin() as conn:
            job = conn.execute(text("""
                SELECT status,collector_uuid,lease_token,lease_expires_at,attempt_count
                FROM collection_jobs WHERE job_id=:id
            """), {"id": job_id}).mappings().one()
            if (job["status"] != "running" or job["collector_uuid"] != uid
                    or job["lease_token"] is None or job["attempt_count"] != 1
                    or not conn.execute(text("""
                        SELECT lease_expires_at > now() FROM collection_jobs WHERE job_id=:id
                    """), {"id": job_id}).scalar_one()):
                raise AssertionError(f"committed running reservation missing: {job}")
            if conn.execute(text("""
                SELECT count(*) FROM collection_events
                WHERE job_id=:id AND event_type='collection_attempt_started'
            """), {"id": job_id}).scalar_one():
                raise AssertionError("start event committed despite injected failure")
            if _usage(conn).total != 1:
                raise AssertionError("unexpired running reservation not charged once")
        print("PASS: production start INSERT failure propagated; HTTP blocked")
        print("PASS: no committed start event; running reservation remains charged once")
        print("Battlelog requests: 0")
    finally:
        try:
            if preflight:
                with engine.begin() as conn:
                    conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('bf4ps:stage9c-fi2-fixture'))"))
                    events = conn.execute(text("""
                        DELETE FROM collection_events WHERE job_id=:id AND collector_uuid=:uid
                    """), {"id": job_id, "uid": uid}).rowcount
                    jobs = conn.execute(text("""
                        DELETE FROM collection_jobs WHERE job_id=:id AND reason=:name
                    """), {"id": job_id, "name": name}).rowcount
                    soldiers = conn.execute(text("""
                        DELETE FROM soldiers WHERE soldier_id=:id AND current_name=:name
                    """), {"id": soldier_id, "name": name}).rowcount
                    collectors = conn.execute(text("""
                        DELETE FROM collectors WHERE collector_uuid=:uid AND collector_name=:name
                    """), {"uid": uid, "name": name}).rowcount
                    gates = conn.execute(text("""
                        DELETE FROM request_gates WHERE egress_key=:name
                    """), {"name": name}).rowcount
                    if (events, jobs, soldiers, collectors, gates) != (
                        0, 1 if seeded else 0, 1 if seeded else 0,
                        1 if seeded else 0, 1 if seeded else 0
                    ):
                        raise RuntimeError("REFUSING partial FI-2 scratch cleanup: "
                                           f"{(events, jobs, soldiers, collectors, gates)}")
                print("PASS: exact scratch fixture and request-gate cleanup")
        finally:
            engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    url = os.environ.get("BF4PS_STAGE9C_INTEGRATION_URL", "")
    if not url:
        parser.error("BF4PS_STAGE9C_INTEGRATION_URL required")
    refuse_unsafe_target(url)
    if not args.execute:
        print("DRY RUN: requires --execute for isolated scratch DB")
        return
    run(url)


if __name__ == "__main__":
    main()
