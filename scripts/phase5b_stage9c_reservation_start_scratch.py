#!/usr/bin/env python3
"""Stage 9C production reservation-to-start accounting on isolated scratch only.

No HTTP. Requires --execute, exact scratch target checks, empty fixtures.
Run from repository root: python -m scripts.phase5b_stage9c_reservation_start_scratch
"""
from __future__ import annotations

import argparse
import os
from uuid import uuid4

from sqlalchemy import create_engine, text

from bf4ps.background_service import (
    BACKGROUND_SLOTS_PER_HOUR, _usage, claim_production_background_job,
)
from bf4ps.collection_jobs import mark_job_running
from bf4ps.detailed_collector import CollectorIdentity, _record_detailed_attempt_started
from scripts.phase5b_stage9c_abort_drain_scratch import check
from scripts.phase5b_stage9c_postgres_integration import refuse_unsafe_target

MARKER = "stage9c_reservation_start"


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
    started = False
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
                    jsonb_build_object('stage9c_reservation_start_marker',
                                       CAST(:marker AS text),
                                       'priority_class','active','retry',false)
                FROM generate_series(1,:n)
            """), {"marker": marker, "n": BACKGROUND_SLOTS_PER_HOUR - 1})
        seeded = True

        with engine.begin() as conn:
            if _usage(conn).total != BACKGROUND_SLOTS_PER_HOUR - 1:
                raise AssertionError("incorrect baseline usage")
            job = claim_production_background_job(
                conn, collector_uuid=uid, resource="detailed",
                allowed_soldier_ids=soldiers,
            )
            if job is None or job.job_id != jobs[0] or job.attempt_count != 1:
                raise AssertionError(f"unexpected claimed job: {job}")
            if _usage(conn).total != BACKGROUND_SLOTS_PER_HOUR:
                raise AssertionError("uncommitted reservation not charged")
            if not mark_job_running(conn, job):
                raise AssertionError("running transition rejected")

        with engine.connect() as conn:
            if _usage(conn).total != BACKGROUND_SLOTS_PER_HOUR:
                raise AssertionError("committed reservation not visible")
            persona_id = int(conn.execute(text(
                "SELECT persona_id FROM soldiers WHERE soldier_id=:sid"
            ), {"sid": job.soldier_id}).scalar_one())
            conn.rollback()

        # Actual production start writer commits in a separate transaction.
        # No collector HTTP function is called by this harness.
        _record_detailed_attempt_started(
            engine, job=job, identity=identity, persona_id=persona_id,
            platform="pc",
        )
        started = True

        with engine.begin() as conn:
            matching = int(conn.execute(text("""
                SELECT count(*) FROM collection_events
                WHERE job_id=:jid AND attempt_number=:attempt
                  AND event_type='collection_attempt_started'
            """), {"jid": job.job_id, "attempt": job.attempt_count}).scalar_one())
            if matching != 1:
                raise AssertionError(f"expected one start event, got {matching}")
            reservation = int(conn.execute(text("""
                SELECT count(*) FROM collection_jobs j
                WHERE j.job_id=:jid AND j.status IN ('claimed','running')
                  AND NOT EXISTS (
                      SELECT 1 FROM collection_events e
                      WHERE e.job_id=j.job_id
                        AND e.attempt_number=j.attempt_count
                        AND e.event_type='collection_attempt_started'
                  )
            """), {"jid": job.job_id}).scalar_one())
            if reservation or _usage(conn).total != BACKGROUND_SLOTS_PER_HOUR:
                raise AssertionError("reservation was not replaced exactly once")
            if claim_production_background_job(
                conn, collector_uuid=uid, resource="detailed",
                allowed_soldier_ids=soldiers,
            ) is not None:
                raise AssertionError("second claim exceeded hourly ceiling")
        print("PASS: production start event replaces committed reservation")
        print("PASS: aggregate usage remains 1296; next claim denied")
        print("Battlelog requests: 0")
    finally:
        try:
            if preflight:
                with engine.begin() as conn:
                    conn.execute(text(
                        "SELECT pg_advisory_xact_lock(hashtext('bf4ps:stage9c-reservation-start-fixture'))"
                    ))
                    counts = (
                        conn.execute(text(
                            "DELETE FROM collection_jobs WHERE job_id=ANY(:ids) AND reason=:reason"
                        ), {"ids": jobs, "reason": name}).rowcount,
                        conn.execute(text("""
                            DELETE FROM collection_events
                            WHERE metadata->>'stage9c_reservation_start_marker'=:marker
                               OR (job_id=ANY(:ids) AND collector_uuid=:uid
                                   AND event_type='collection_attempt_started')
                        """), {"marker": marker, "ids": jobs, "uid": uid}).rowcount,
                        conn.execute(text("""
                            DELETE FROM soldiers
                            WHERE soldier_id=ANY(:ids) AND current_name LIKE :prefix
                        """), {"ids": soldiers, "prefix": name + "-%"}).rowcount,
                        conn.execute(text("""
                            DELETE FROM collectors
                            WHERE collector_uuid=:uid AND collector_name=:name
                        """), {"uid": uid, "name": name}).rowcount,
                    )
                    expected = (
                        (2, BACKGROUND_SLOTS_PER_HOUR - 1 + int(started), 2, 1)
                        if seeded else (0, 0, 0, 0)
                    )
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
