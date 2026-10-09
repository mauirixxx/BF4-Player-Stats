#!/usr/bin/env python3
"""T2 physical-start duplicate/concurrency/retry scratch proof. Zero HTTP."""
from __future__ import annotations

import argparse
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

from sqlalchemy import create_engine, text

from bf4ps.collection_jobs import ClaimedJob
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
    marker = "stage9c_t2_" + str(uid)
    soldiers = []
    jobs = []
    seeded = False
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
                    (soldier_id,resource,lane,priority_class,reason,status,priority_value,
                     eligible_at,attempt_count,collector_uuid,lease_token,claimed_at,
                     started_at,lease_expires_at)
                    VALUES (:sid,:resource,'background','active',:reason,'running',0,
                            now(),1,:uid,:token,now(),now(),now()+interval '30 minutes')
                    RETURNING job_id
                """), {"sid": sid, "resource": resource, "reason": marker,
                       "uid": uid, "token": uuid4()}).scalar_one()
                jobs.append(int(jid))
        seeded = True
        for index, (resource, identity_type, writer) in enumerate(WRITERS):
            identity = identity_type(collector_uuid=uid, collector_name=marker,
                                     hostname="stage9c-scratch", egress_key=marker,
                                     lane="background")
            with engine.connect() as conn:
                row = conn.execute(text("""
                    SELECT job_id,soldier_id,resource,lane,attempt_count,collector_uuid,lease_token
                    FROM collection_jobs WHERE job_id=:jid
                """), {"jid": jobs[index]}).mappings().one()
                job = ClaimedJob(**row)
                persona = conn.execute(text(
                    "SELECT persona_id FROM soldiers WHERE soldier_id=:sid"
                ), {"sid": job.soldier_id}).scalar_one()
                conn.rollback()

            gate = Barrier(2)
            def contender():
                gate.wait(timeout=10)
                try:
                    writer(engine, job=job, identity=identity,
                           persona_id=persona, platform="pc")
                    return "started"
                except RuntimeError as exc:
                    if "physical start already recorded" not in str(exc):
                        raise
                    return "duplicate_rejected"
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(contender) for _ in range(2)]
                results = sorted(f.result(timeout=20) for f in futures)
            if results != ["duplicate_rejected", "started"]:
                raise AssertionError(f"{resource} concurrent starts: {results}")
            try:
                writer(engine, job=job, identity=identity,
                       persona_id=persona, platform="pc")
            except RuntimeError as exc:
                if "physical start already recorded" not in str(exc):
                    raise
            else:
                raise AssertionError(f"{resource} sequential duplicate accepted")
            with engine.begin() as conn:
                count = conn.execute(text("""
                    SELECT count(*) FROM collection_events
                    WHERE job_id=:jid AND event_type='collection_attempt_started'
                      AND attempt_number=1 AND metadata->>'physical_request'='true'
                """), {"jid": job.job_id}).scalar_one()
                if count != 1:
                    raise AssertionError(f"{resource} first attempt has {count} starts")
                new_token = uuid4()
                conn.execute(text("""
                    UPDATE collection_jobs SET attempt_count=2, lease_token=:token,
                        lease_expires_at=now()+interval '30 minutes'
                    WHERE job_id=:jid AND collector_uuid=:uid
                """), {"token": new_token, "jid": job.job_id, "uid": uid})
            next_job = ClaimedJob(job_id=job.job_id, soldier_id=job.soldier_id,
                                  resource=resource, lane="background", attempt_count=2,
                                  collector_uuid=uid, lease_token=new_token)
            writer(engine, job=next_job, identity=identity,
                   persona_id=persona, platform="pc")
            with engine.begin() as conn:
                attempts = conn.execute(text("""
                    SELECT attempt_number,count(*) AS n FROM collection_events
                    WHERE job_id=:jid AND event_type='collection_attempt_started'
                      AND metadata->>'physical_request'='true'
                    GROUP BY attempt_number ORDER BY attempt_number
                """), {"jid": job.job_id}).all()
                if [(int(a), int(n)) for a, n in attempts] != [(1, 1), (2, 1)]:
                    raise AssertionError(f"{resource} attempt ledger: {attempts}")
            print(f"PASS: {resource} concurrent + sequential duplicate rejected; retry attempt 2 accepted")
        print("Real HTTP requests: 0")
    finally:
        try:
            if preflight:
                with engine.begin() as conn:
                    conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('bf4ps:stage9c-reservation-start-fixture'))"))
                    events = conn.execute(text("""
                        DELETE FROM collection_events
                        WHERE job_id=ANY(:jobs) AND collector_uuid=:uid
                          AND event_type='collection_attempt_started'
                    """), {"jobs": jobs, "uid": uid}).rowcount
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
                    expected = (6, 3, 3, 1) if seeded else (0, 0, 0, 0)
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
