#!/usr/bin/env python3
"""Full detailed collector diagnostic after rolled-back success (scratch only).

No HTTP. Requires --execute, exact scratch target checks, empty fixtures.
Run from repository root: python -m scripts.phase5b_stage9c_detailed_orchestrator_scratch
"""
from __future__ import annotations

import argparse
import os
from uuid import uuid4
from types import SimpleNamespace
from unittest.mock import patch
from bf4ps.battlelog_detailed import DetailedFetchResult
from sqlalchemy import event
from bf4ps.detailed_persistence import DETAILED_FIELDS

from sqlalchemy import create_engine, text

from bf4ps.background_service import (
    BACKGROUND_SLOTS_PER_HOUR, _usage, claim_production_background_job,
)
from bf4ps.detailed_collector import CollectorIdentity, collect_one_detailed_job
from scripts.phase5b_stage9c_abort_drain_scratch import check
from scripts.phase5b_stage9c_postgres_integration import refuse_unsafe_target

MARKER = "stage9c_detailed_orchestrator"


def run(url: str) -> None:
    refuse_unsafe_target(url)
    engine = create_engine(
        url, pool_size=3, max_overflow=0, pool_pre_ping=True,
        connect_args={"connect_timeout": 5, "options": "-c statement_timeout=15000"},
    )
    marker = str(uuid4())
    uid = uuid4()
    name = f"{MARKER}-{marker}"
    identity = CollectorIdentity(
        collector_uuid=uid, collector_name=name, hostname="stage9c-scratch",
        egress_key=name, lane="background",
    )
    soldiers: list[int] = []
    jobs: list[int] = []
    seeded = False
    preflight = False
    try:
        with engine.connect() as conn:
            check(conn)
            for table in ("collectors", "soldiers", "collection_jobs",
                          "collection_events", "stage9c_supervision_runs"):
                if conn.execute(text(f"SELECT count(*) FROM public.{table}")).scalar_one():
                    raise RuntimeError(f"REFUSING nonempty {table}")
            if conn.execute(text("SHOW transaction_isolation")).scalar_one().lower() != "read committed":
                raise RuntimeError("REFUSING non-READ COMMITTED isolation")
            conn.rollback()
        preflight = True

        with engine.begin() as conn:
            conn.execute(text(
                "SELECT pg_advisory_xact_lock(hashtext('bf4ps:stage9c-reservation-start-fixture'))"
            ))
            for table in ("collectors", "soldiers", "collection_jobs",
                          "collection_events", "stage9c_supervision_runs"):
                if conn.execute(text(f"SELECT count(*) FROM public.{table}")).scalar_one():
                    raise RuntimeError(f"REFUSING concurrently populated {table}")
            conn.execute(text("""
                INSERT INTO collectors
                    (collector_uuid,collector_name,hostname,lane,egress_key,
                     enabled,drained,heartbeat_state)
                VALUES (:uid,:name,'stage9c-scratch','background',:name,true,false,'healthy')
            """), {"uid": uid, "name": name})
            for i in range(2):
                sid = int(conn.execute(text("""
                    INSERT INTO soldiers
                        (persona_id,platform,current_name,first_seen_at,last_seen_at)
                    VALUES (:persona,'pc',:name,now(),now()) RETURNING soldier_id
                """), {"persona": 800000000000 + i + int(uid.int % 10000000),
                       "name": f"{name}-{i}"}).scalar_one())
                soldiers.append(sid)
                jid = int(conn.execute(text("""
                    INSERT INTO collection_jobs
                        (soldier_id,resource,lane,priority_class,reason,
                         status,priority_value,eligible_at)
                    VALUES (:sid,'detailed','background','active',:reason,
                            'pending',0,now()) RETURNING job_id
                """), {"sid": sid, "reason": name}).scalar_one())
                jobs.append(jid)
            conn.execute(text("""
                INSERT INTO collection_events
                    (resource,lane,event_type,attempt_number,metadata)
                SELECT 'detailed','background','collection_attempt_started',1,
                    jsonb_build_object('stage9c_detailed_orchestrator_marker',
                                       CAST(:marker AS text),
                                       'priority_class','active','retry',false)
                FROM generate_series(1,:n)
            """), {"marker": marker, "n": BACKGROUND_SLOTS_PER_HOUR - 1})
        seeded = True

        # Exercise the complete production collector path, not a helper call.
        # Fake the network boundary and normalization; any real HTTP is forbidden.
        injected = {"count": 0}
        http_calls = {"count": 0}
        def fake_fetch(persona_id, platform, *, timeout_seconds):
            http_calls["count"] += 1
            return DetailedFetchResult(
                persona_id=persona_id, platform=platform, platform_int=1, payload={},
            )
        def fake_normalize(payload, *, expected_persona_id, expected_platform_int):
            return {field: None for field in DETAILED_FIELDS}
        def fail_success(conn, cursor, statement, parameters, context, executemany):
            if ("INSERT INTO collection_events" in statement
                    and "'collection_success'" in statement):
                injected["count"] += 1
                raise RuntimeError("ORCH injected persistence INSERT failure")
        event.listen(engine, "before_cursor_execute", fail_success)
        try:
            with patch("bf4ps.detailed_collector.fetch_detailed_stats", side_effect=fake_fetch), \
                 patch("bf4ps.detailed_collector.normalize_detailed_stats", side_effect=fake_normalize), \
                 patch("bf4ps.battlelog_detailed.urlopen", side_effect=AssertionError("REAL HTTP FORBIDDEN")):
                try:
                    collect_one_detailed_job(
                        engine, identity=identity, request_interval_seconds=0,
                        allowed_soldier_ids=soldiers, enforce_production_budget=True,
                    )
                except RuntimeError as exc:
                    if str(exc) != "ORCH injected persistence INSERT failure":
                        raise
                else:
                    raise AssertionError("collector swallowed original persistence error")
        finally:
            event.remove(engine, "before_cursor_execute", fail_success)
        if injected["count"] != 1 or http_calls["count"] != 1:
            raise AssertionError(f"unexpected injected/virtual-fetch counts: {injected}, {http_calls}")

        with engine.connect() as conn:
            row = conn.execute(text("""
                SELECT job_id, soldier_id, attempt_count, lease_token
                FROM collection_jobs
                WHERE job_id=:jid
            """), {"jid": jobs[0]}).mappings().one()
            job = SimpleNamespace(**row)
            conn.rollback()

        # Independent transaction observes start retained, and all
        # persistence writes rolled back (including current/history/state).
        with engine.begin() as conn:
            matching = int(conn.execute(text("""
                SELECT count(*) FROM collection_events
                WHERE job_id=:jid AND attempt_number=:attempt
                  AND event_type='collection_attempt_started'
                  AND metadata->>'physical_request'='true'
            """), {"jid": job.job_id, "attempt": job.attempt_count}).scalar_one())
            if matching != 1:
                raise AssertionError(f"durable physical start missing: {matching}")
            for table in ("detailed_stats_current", "detailed_stats_history", "collection_state"):
                count = conn.execute(text(
                    f"SELECT count(*) FROM {table} WHERE soldier_id=:sid"
                ), {"sid": job.soldier_id}).scalar_one()
                if count:
                    raise AssertionError(f"rolled-back persistence remains in {table}: {count}")
            diagnostic = conn.execute(text("""
                SELECT count(*) FROM collection_events
                WHERE job_id=:jid AND event_type='collection_persistence_failure'
                  AND attempt_number=:attempt
                  AND metadata->>'stage'='persist_detailed_success'
                  AND error_message='ORCH injected persistence INSERT failure'
            """), {"jid": job.job_id, "attempt": job.attempt_count}).scalar_one()
            if diagnostic != 1:
                raise AssertionError(f"expected one committed diagnostic: {diagnostic}")
            success = conn.execute(text("""
                SELECT count(*) FROM collection_events
                WHERE job_id=:jid AND event_type='collection_success'
            """), {"jid": job.job_id}).scalar_one()
            if success:
                raise AssertionError("success event committed despite rollback")
            state = conn.execute(text("""
                SELECT status, collector_uuid, lease_token, attempt_count,
                       lease_expires_at > now() AS lease_valid
                FROM collection_jobs WHERE job_id=:jid
            """), {"jid": job.job_id}).mappings().one()
            if (state["status"] != "running" or state["collector_uuid"] != uid
                    or state["lease_token"] != job.lease_token
                    or state["attempt_count"] != job.attempt_count
                    or not state["lease_valid"]):
                raise AssertionError(f"running ownership lost: {state}")
            if _usage(conn).total != BACKGROUND_SLOTS_PER_HOUR:
                raise AssertionError("committed physical attempt not charged after rollback")
            if claim_production_background_job(
                conn, collector_uuid=uid, resource="detailed",
                allowed_soldier_ids=soldiers,
            ) is not None:
                raise AssertionError("post-rollback claim exceeded hourly ceiling")
        print("PASS: detailed diagnostic event committed after persistence rollback")
        print("PASS: committed physical start survives later persistence rollback")
        print("PASS: current/history/state/success rolled back; slot 1296 remains charged")
        print("Real Battlelog requests: 0 (one mocked fetch)")
    finally:
        try:
            if preflight:
                with engine.begin() as conn:
                    conn.execute(text(
                        "SELECT pg_advisory_xact_lock(hashtext('bf4ps:stage9c-reservation-start-fixture'))"
                    ))
                    # Remove start events before jobs: FK ON DELETE SET NULL
                    # would otherwise erase the job_id cleanup selector.
                    deleted_events = conn.execute(text("""
                        DELETE FROM collection_events
                        WHERE metadata->>'stage9c_detailed_orchestrator_marker'=:marker
                           OR (job_id=ANY(:ids) AND collector_uuid=:uid
                               AND event_type IN ('collection_attempt_started','collection_persistence_failure'))
                    """), {"marker": marker, "ids": jobs, "uid": uid}).rowcount
                    deleted_jobs = conn.execute(text(
                        "DELETE FROM collection_jobs WHERE job_id=ANY(:ids) AND reason=:reason"
                    ), {"ids": jobs, "reason": name}).rowcount
                    deleted_soldiers = conn.execute(text("""
                        DELETE FROM soldiers
                        WHERE soldier_id=ANY(:ids) AND current_name LIKE :prefix
                    """), {"ids": soldiers, "prefix": name + "-%"}).rowcount
                    conn.execute(text("DELETE FROM request_gates WHERE egress_key=:name"), {"name": name})
                    deleted_collectors = conn.execute(text("""
                        DELETE FROM collectors
                        WHERE collector_uuid=:uid AND collector_name=:name
                    """), {"uid": uid, "name": name}).rowcount
                    counts = (deleted_jobs, deleted_events, deleted_soldiers, deleted_collectors)
                    # The production writer commits independently. If it committed
                    # and then raised, an in-memory flag is not authoritative.
                    # Exactly 1295 baseline events, one owned start, and one diagnostic
                    # event are valid for this test; anything else fails closed.
                    baseline = BACKGROUND_SLOTS_PER_HOUR - 1
                    valid_events = {baseline + 2} if seeded else {0}
                    expected_shape = (2, 2, 1) if seeded else (0, 0, 0)
                    if deleted_events not in valid_events:
                        raise RuntimeError(
                            f"REFUSING unexpected event cleanup count: {deleted_events}"
                        )
                    expected = (expected_shape[0], deleted_events,
                                expected_shape[1], expected_shape[2])
                    if counts != expected:
                        raise RuntimeError(f"REFUSING partial cleanup: {counts} != {expected}")
                print("PASS: exact scratch fixture cleanup")
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
