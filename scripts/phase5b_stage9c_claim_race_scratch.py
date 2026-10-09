#!/usr/bin/env python3
"""Actual production background claim race at 1295/1296 on Stage 9C scratch.

Independent PostgreSQL connections; synthetic FK-valid committed fixtures;
no HTTP, systemd, migrations, or production targets. Requires --execute.
"""
from __future__ import annotations

import argparse
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

from sqlalchemy import create_engine, text

from bf4ps.background_service import BACKGROUND_SLOTS_PER_HOUR, _usage, claim_production_background_job
from scripts.phase5b_stage9c_abort_drain_scratch import check
from scripts.phase5b_stage9c_postgres_integration import refuse_unsafe_target

MARKER = "stage9c_claim_race"


def run(url):
    refuse_unsafe_target(url)
    engine = create_engine(url, pool_size=4, max_overflow=0, pool_pre_ping=True,
                           connect_args={"connect_timeout": 5, "options": "-c statement_timeout=15000"})
    marker = str(uuid4())
    collectors, soldiers, jobs = [], [], []
    seeded = False
    preflight_passed = False
    ready, second_ready, release = Event(), Event(), Event()
    try:
        with engine.connect() as conn:
            check(conn)
            for table in ("collectors", "soldiers", "collection_jobs", "collection_events",
                          "stage9c_supervision_runs"):
                if conn.execute(text(f"SELECT count(*) FROM public.{table}")).scalar_one():
                    raise RuntimeError(f"REFUSING nonempty {table}")
            if conn.execute(text("SHOW transaction_isolation")).scalar_one().lower() != "read committed":
                raise RuntimeError("REFUSING non-READ COMMITTED isolation")
            conn.rollback()
        preflight_passed = True
        with engine.begin() as conn:
            # Serialize scratch preflight against other runs of this harness.
            # Recheck emptiness after acquiring the transaction lock.
            conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('bf4ps:stage9c-claim-race-fixture'))"))
            for table in ('collectors','soldiers','collection_jobs','collection_events','stage9c_supervision_runs'):
                if conn.execute(text(f'SELECT count(*) FROM public.{table}')).scalar_one():
                    raise RuntimeError(f'REFUSING concurrently populated scratch table: {table}')
            for i, resource in enumerate(("weapons", "vehicles")):
                uid = uuid4()
                collectors.append(uid)
                conn.execute(text("""
                    INSERT INTO collectors
                      (collector_uuid,collector_name,hostname,lane,egress_key,enabled,drained,heartbeat_state)
                    VALUES (:uid,:name,'stage9c-scratch','background',:egress,true,false,'healthy')
                """), {"uid": uid, "name": f"{MARKER}-{marker}-{i}", "egress": f"{MARKER}-{marker}-{i}"})
                sid = int(conn.execute(text("""
                    INSERT INTO soldiers
                      (persona_id,platform,current_name,first_seen_at,last_seen_at)
                    VALUES (:persona,'pc',:name,now(),now()) RETURNING soldier_id
                """), {"persona": 800000000000 + i + int(uid.int % 10000000),
                       "name": f"{MARKER}-{marker}-{i}"}).scalar_one())
                soldiers.append(sid)
                jobid = int(conn.execute(text("""
                    INSERT INTO collection_jobs
                      (soldier_id,resource,lane,priority_class,reason,status,priority_value,eligible_at)
                    VALUES (:sid,:resource,'background','active',:reason,'pending',0,now())
                    RETURNING job_id
                """), {"sid": sid, "resource": resource, "reason": f"{MARKER}-{marker}"}).scalar_one())
                jobs.append(jobid)
            conn.execute(text("""
                INSERT INTO collection_events
                  (resource,lane,event_type,attempt_number,metadata)
                SELECT 'detailed','background','collection_attempt_started',1,
                       jsonb_build_object('stage9c_claim_race_marker',CAST(:marker AS text),
                                          'priority_class','active','retry',false)
                FROM generate_series(1,:n)
            """), {"marker": marker, "n": BACKGROUND_SLOTS_PER_HOUR - 1})
        seeded = True

        def first():
            with engine.begin() as conn:
                claim = claim_production_background_job(
                    conn, collector_uuid=collectors[0], resource="weapons",
                    allowed_soldier_ids=soldiers)
                if claim is None or claim.job_id != jobs[0]:
                    raise AssertionError(f"first claim wrong: {claim}")
                if _usage(conn).total != BACKGROUND_SLOTS_PER_HOUR:
                    raise AssertionError("uncommitted reservation did not count")
                ready.set()
                if not release.wait(timeout=10):
                    raise TimeoutError("first claim held too long")
                return claim

        def second():
            if not ready.wait(timeout=10):
                raise TimeoutError("first claim never acquired lock")
            with engine.begin() as conn:
                second_ready.set()
                claim = claim_production_background_job(
                    conn, collector_uuid=collectors[1], resource="vehicles",
                    allowed_soldier_ids=soldiers)
                if claim is not None:
                    raise AssertionError(f"1297th claim admitted: {claim}")
                return _usage(conn).total

        with ThreadPoolExecutor(max_workers=2) as pool:
            a, b = pool.submit(first), pool.submit(second)
            if not ready.wait(timeout=10) or not second_ready.wait(timeout=10):
                raise TimeoutError("race barrier not reached")
            with engine.begin() as probe:
                if probe.execute(text("""
                    SELECT pg_try_advisory_xact_lock(hashtext('bf4ps:phase5b-background-service'))
                """)).scalar_one():
                    raise AssertionError("first claim does not hold admission lock")
            release.set()
            winner = a.result(timeout=20)
            assert b.result(timeout=20) == BACKGROUND_SLOTS_PER_HOUR

        with engine.connect() as conn:
            assert _usage(conn).total == BACKGROUND_SLOTS_PER_HOUR
            rows = conn.execute(text("""
                SELECT job_id,status,attempt_count,collector_uuid,lease_token
                FROM collection_jobs WHERE job_id = ANY(:ids)
            """), {"ids": jobs}).mappings().all()
            assert len(rows) == 2
            assert sum(row["status"] == "claimed" for row in rows) == 1
            assert sum(row["status"] == "pending" for row in rows) == 1
            assert any(row["job_id"] == winner.job_id and
                       row["collector_uuid"] == winner.collector_uuid and
                       row["lease_token"] == winner.lease_token for row in rows)
            conn.rollback()
        print("PASS: real production claim at 1295 reserves final slot")
        print("PASS: independent competing vehicles claim denied at 1296")
        print("PASS: committed reservation and lease ownership reconciled")
        print("Battlelog requests: 0")
    finally:
        release.set()
        try:
            if preflight_passed:
                with engine.begin() as conn:
                    # Cleanup is all-or-nothing; unexpected counts abort the
                    # transaction instead of committing partial deletions.
                    conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('bf4ps:stage9c-claim-race-fixture'))"))
                    deleted_jobs = conn.execute(text("""
                        DELETE FROM collection_jobs
                        WHERE job_id=ANY(:ids) AND reason=:reason
                    """), {"ids": jobs, "reason": f"{MARKER}-{marker}"}).rowcount
                    deleted_events = conn.execute(text("""
                        DELETE FROM collection_events
                        WHERE metadata->>'stage9c_claim_race_marker'=:marker
                    """), {"marker": marker}).rowcount
                    deleted_soldiers = conn.execute(text("""
                        DELETE FROM soldiers
                        WHERE soldier_id=ANY(:ids) AND current_name LIKE :prefix
                    """), {"ids": soldiers, "prefix": f"{MARKER}-{marker}-%"}).rowcount
                    deleted_collectors = conn.execute(text("""
                        DELETE FROM collectors
                        WHERE collector_uuid=ANY(:ids) AND collector_name LIKE :prefix
                    """), {"ids": collectors, "prefix": f"{MARKER}-{marker}-%"}).rowcount
                    expected = (2, BACKGROUND_SLOTS_PER_HOUR - 1, 2, 2) if seeded else (0, 0, 0, 0)
                    actual = (deleted_jobs, deleted_events, deleted_soldiers, deleted_collectors)
                    if actual != expected:
                        raise RuntimeError(f"REFUSING partial scratch cleanup: {actual} != {expected}")
                print("PASS: exact scratch fixture cleanup")
        finally:
            engine.dispose()


def main():
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
