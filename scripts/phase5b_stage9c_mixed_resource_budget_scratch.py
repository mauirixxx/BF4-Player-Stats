#!/usr/bin/env python3
"""T1 shared mixed-resource hourly budget and retry scratch proof. Zero HTTP."""
from __future__ import annotations

import argparse
import os
from uuid import uuid4

from sqlalchemy import create_engine, text

from bf4ps.collection_jobs import mark_job_running
from bf4ps.background_service import BACKGROUND_SLOTS_PER_HOUR, _usage, claim_production_background_job
from bf4ps.detailed_collector import (
    CollectorIdentity as DetailedIdentity, _record_detailed_attempt_started,
)
from bf4ps.weapon_collector import (
    CollectorIdentity as WeaponIdentity, _record_attempt_started,
)
from bf4ps.vehicle_collector import (
    CollectorIdentity as VehicleIdentity, _record_vehicle_attempt_started,
)
from scripts.phase5b_stage9c_abort_drain_scratch import check
from scripts.phase5b_stage9c_postgres_integration import refuse_unsafe_target

WRITERS = (
    ("detailed", DetailedIdentity, _record_detailed_attempt_started),
    ("weapons", WeaponIdentity, _record_attempt_started),
    ("vehicles", VehicleIdentity, _record_vehicle_attempt_started),
)
TABLES = ("collectors", "soldiers", "collection_jobs", "collection_events",
          "stage9c_supervision_runs")


def run(url: str) -> None:
    refuse_unsafe_target(url)
    engine = create_engine(url, pool_size=4, max_overflow=0, pool_pre_ping=True,
                           connect_args={"connect_timeout": 5,
                                         "options": "-c statement_timeout=15000"})
    uid = uuid4()
    marker = "stage9c_t1_" + str(uid)
    soldiers = []
    jobs = []
    seeded = False
    synthetic_count = BACKGROUND_SLOTS_PER_HOUR - 3
    preflight = False
    try:
        with engine.connect() as conn:
            check(conn)
            for table in TABLES:
                if conn.execute(text(f"SELECT count(*) FROM public.{table}")).scalar_one():
                    raise RuntimeError(f"REFUSING nonempty {table}")
            if conn.execute(text("SHOW transaction_isolation")).scalar_one().lower() != "read committed":
                raise RuntimeError("REFUSING non-READ COMMITTED isolation")
            conn.rollback()
        preflight = True
        with engine.begin() as conn:
            conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('bf4ps:stage9c-reservation-start-fixture'))"))
            for table in TABLES:
                if conn.execute(text(f"SELECT count(*) FROM public.{table}")).scalar_one():
                    raise RuntimeError(f"REFUSING concurrently populated {table}")
            conn.execute(text("""
                INSERT INTO collectors
                (collector_uuid,collector_name,hostname,lane,egress_key,enabled,drained,heartbeat_state)
                VALUES (:uid,:name,'stage9c-scratch','background',:name,true,false,'healthy')
            """), {"uid": uid, "name": marker})
            for index, (resource, _, _) in enumerate(WRITERS):
                persona = 880000000000 + int(uid.int % 10000000) + index
                sid = conn.execute(text("""
                    INSERT INTO soldiers
                    (persona_id,platform,current_name,first_seen_at,last_seen_at)
                    VALUES (:persona,'pc',:name,now(),now()) RETURNING soldier_id
                """), {"persona": persona, "name": marker + "-" + resource}).scalar_one()
                soldiers.append(int(sid))
                jid = conn.execute(text("""
                    INSERT INTO collection_jobs
                    (soldier_id,resource,lane,priority_class,reason,status,priority_value,eligible_at)
                    VALUES (:sid,:resource,'background','active',:reason,'pending',0,now())
                    RETURNING job_id
                """), {"sid": sid, "resource": resource, "reason": marker}).scalar_one()
                jobs.append(int(jid))
            conn.execute(text("""
                INSERT INTO collection_events
                    (resource,lane,event_type,attempt_number,metadata)
                SELECT CASE WHEN n % 3 = 0 THEN 'detailed'
                            WHEN n % 3 = 1 THEN 'weapons' ELSE 'vehicles' END,
                       'background','collection_attempt_started',1,
                       jsonb_build_object('stage9c_t1_marker',CAST(:marker AS text),
                                          'priority_class','active','retry',false)
                FROM generate_series(1,:n) AS n
            """), {"marker": marker, "n": synthetic_count})
        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE collection_jobs SET last_error_at=now(),
                    last_error_class='stage9c_synthetic_retry'
                WHERE job_id=:jid
            """), {"jid": jobs[2]})
        seeded = True
        for index, (resource, identity_type, writer) in enumerate(WRITERS):
            identity = identity_type(collector_uuid=uid, collector_name=marker,
                                     hostname="stage9c-scratch", egress_key=marker,
                                     lane="background")
            with engine.begin() as conn:
                before = _usage(conn)
                if before.total != synthetic_count + index:
                    raise AssertionError(f"{resource} pre-claim usage: {before}")
                job = claim_production_background_job(
                    conn, collector_uuid=uid, resource=resource,
                    allowed_soldier_ids=soldiers,
                )
                if job is None or job.job_id != jobs[index]:
                    raise AssertionError(f"{resource} claim denied unexpectedly")
                if not mark_job_running(conn, job):
                    raise AssertionError(f"{resource} mark running rejected")
                reserved = _usage(conn)
                if reserved.total != before.total + 1:
                    raise AssertionError(f"{resource} reservation not charged: {reserved}")
            with engine.begin() as conn:
                persona = conn.execute(text(
                    "SELECT persona_id FROM soldiers WHERE soldier_id=:sid"
                ), {"sid": job.soldier_id}).scalar_one()
            writer(engine, job=job, identity=identity,
                   persona_id=persona, platform="pc")
            with engine.begin() as conn:
                after = _usage(conn)
                if after.total != synthetic_count + index + 1:
                    raise AssertionError(f"{resource} start double-counted: {after}")
                event = conn.execute(text("""
                    SELECT metadata->>'retry' FROM collection_events
                    WHERE job_id=:jid AND event_type='collection_attempt_started'
                      AND attempt_number=1
                """), {"jid": job.job_id}).scalar_one()
                expected_retry = "true" if resource == "vehicles" else "false"
                if event != expected_retry:
                    raise AssertionError(f"{resource} retry marker {event} != {expected_retry}")
            print(f"PASS: {resource} reservation converted to one charged start")
        with engine.begin() as conn:
            usage = _usage(conn)
            if usage.total != BACKGROUND_SLOTS_PER_HOUR:
                raise AssertionError(f"mixed-resource hourly cap not reached: {usage}")
            if claim_production_background_job(
                conn, collector_uuid=uid, resource="detailed",
                allowed_soldier_ids=soldiers,
            ) is not None:
                raise AssertionError("cap permitted additional detailed claim")
            if claim_production_background_job(
                conn, collector_uuid=uid, resource="weapons",
                allowed_soldier_ids=soldiers,
            ) is not None:
                raise AssertionError("cap permitted additional weapon claim")
            if claim_production_background_job(
                conn, collector_uuid=uid, resource="vehicles",
                allowed_soldier_ids=soldiers,
            ) is not None:
                raise AssertionError("cap permitted additional vehicle claim")
        print("PASS: shared 1296/hour cap blocks all three resources")
        print("PASS: retry-classified vehicle attempt included in global cap")
        print("Real HTTP requests: 0")
    finally:
        try:
            if preflight:
                with engine.begin() as conn:
                    conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('bf4ps:stage9c-reservation-start-fixture'))"))
                    events = conn.execute(text("""
                        DELETE FROM collection_events
                        WHERE (job_id=ANY(:jobs) AND collector_uuid=:uid
                          AND event_type='collection_attempt_started')
                           OR metadata->>'stage9c_t1_marker'=:marker
                    """), {"jobs": jobs, "uid": uid, "marker": marker}).rowcount
                    deleted_jobs = conn.execute(text("""
                        DELETE FROM collection_jobs WHERE job_id=ANY(:jobs) AND reason=:marker
                    """), {"jobs": jobs, "marker": marker}).rowcount
                    deleted_soldiers = conn.execute(text("""
                        DELETE FROM soldiers WHERE soldier_id=ANY(:soldiers)
                          AND current_name LIKE :prefix
                    """), {"soldiers": soldiers, "prefix": marker + "-%"}).rowcount
                    deleted_collector = conn.execute(text("""
                        DELETE FROM collectors WHERE collector_uuid=:uid AND collector_name=:marker
                    """), {"uid": uid, "marker": marker}).rowcount
                    expected = (synthetic_count + 3, 3, 3, 1) if seeded else (0, 0, 0, 0)
                    actual = (events, deleted_jobs, deleted_soldiers, deleted_collector)
                    if actual != expected:
                        raise RuntimeError(f"REFUSING unexpected fixture cleanup {actual} != {expected}")
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
        print("DRY RUN: requires --execute")
        return
    run(url)


if __name__ == "__main__":
    main()
