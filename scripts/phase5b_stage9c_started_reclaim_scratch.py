#!/usr/bin/env python3
"""Stage 9C started-lease expiry and replacement accounting on isolated scratch only.

No HTTP. Requires --execute, exact scratch target checks, empty fixtures.
Run from repository root: python -m scripts.phase5b_stage9c_started_reclaim_scratch
"""
from __future__ import annotations

import argparse
import os
from uuid import uuid4

from sqlalchemy import create_engine, text

from bf4ps.background_service import (
    BACKGROUND_SLOTS_PER_HOUR, _usage, claim_production_background_job,
)
from bf4ps.collection_jobs import mark_job_running, renew_lease, finalize_owned_job
from bf4ps.detailed_collector import CollectorIdentity, _record_detailed_attempt_started
from scripts.phase5b_stage9c_abort_drain_scratch import check
from scripts.phase5b_stage9c_postgres_integration import refuse_unsafe_target

MARKER = "stage9c_started_reclaim"


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
                "SELECT pg_advisory_xact_lock(hashtext('bf4ps:stage9c-started-reclaim-fixture'))"
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
                    jsonb_build_object('stage9c_started_reclaim_marker',
                                       CAST(:marker AS text),
                                       'priority_class','active','retry',false)
                FROM generate_series(1,:n)
            """), {"marker": marker, "n": BACKGROUND_SLOTS_PER_HOUR - 2})
        seeded = True

        with engine.begin() as conn:
            if _usage(conn).total != BACKGROUND_SLOTS_PER_HOUR - 2:
                raise AssertionError("incorrect baseline usage")
            job = claim_production_background_job(
                conn, collector_uuid=uid, resource="detailed",
                allowed_soldier_ids=soldiers,
            )
            if job is None or job.job_id != jobs[0] or job.attempt_count != 1:
                raise AssertionError(f"unexpected claimed job: {job}")
            if _usage(conn).total != BACKGROUND_SLOTS_PER_HOUR - 1:
                raise AssertionError("uncommitted reservation not charged")
            if not mark_job_running(conn, job):
                raise AssertionError("running transition rejected")

        with engine.connect() as conn:
            if _usage(conn).total != BACKGROUND_SLOTS_PER_HOUR - 1:
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

        with engine.begin() as conn:
            matching = int(conn.execute(text("""
                SELECT count(*) FROM collection_events
                WHERE job_id=:jid AND attempt_number=:attempt
                  AND event_type='collection_attempt_started'
            """), {"jid": job.job_id, "attempt": job.attempt_count}).scalar_one())
            if matching != 1 or _usage(conn).total != BACKGROUND_SLOTS_PER_HOUR - 1:
                raise AssertionError("started event did not replace original reservation")
            changed = conn.execute(text("""
                UPDATE collection_jobs
                SET lease_expires_at=now()-interval '1 second', updated_at=now()
                WHERE job_id=:jid AND collector_uuid=:uid AND lease_token=:token
                  AND status='running'
            """), {"jid": job.job_id, "uid": uid, "token": job.lease_token}).rowcount
            if changed != 1:
                raise AssertionError("could not expire exact started fixture")
            if _usage(conn).total != BACKGROUND_SLOTS_PER_HOUR - 1:
                raise AssertionError("expired started attempt was incorrectly discounted")

        with engine.begin() as conn:
            replacement = claim_production_background_job(
                conn, collector_uuid=uid, resource="detailed",
                allowed_soldier_ids=[job.soldier_id],
            )
            if (replacement is None or replacement.job_id != job.job_id
                    or replacement.attempt_count != 2
                    or replacement.lease_token == job.lease_token):
                raise AssertionError(f"started lease reclaim incorrect: {replacement}")
            if _usage(conn).total != BACKGROUND_SLOTS_PER_HOUR:
                raise AssertionError("old start plus new reservation not charged separately")
            if renew_lease(conn, job) or finalize_owned_job(conn, job):
                raise AssertionError("stale started owner altered replacement")
            if _usage(conn).total != BACKGROUND_SLOTS_PER_HOUR:
                raise AssertionError("stale owner changed usage")
            if claim_production_background_job(
                conn, collector_uuid=uid, resource="detailed",
                allowed_soldier_ids=[soldiers[1]],
            ) is not None:
                raise AssertionError("admitted beyond rolling ceiling")
        print("PASS: expired started attempt remains charged")
        print("PASS: replacement reservation separately charged; total 1296")
        print("PASS: stale owner fenced; further admission denied")
        print("Battlelog requests: 0")
    finally:
        try:
            if preflight:
                with engine.begin() as conn:
                    conn.execute(text(
                        "SELECT pg_advisory_xact_lock(hashtext('bf4ps:stage9c-started-reclaim-fixture'))"
                    ))
                    # Remove start events before jobs: FK ON DELETE SET NULL
                    # would otherwise erase the job_id cleanup selector.
                    deleted_events = conn.execute(text("""
                        DELETE FROM collection_events
                        WHERE metadata->>'stage9c_started_reclaim_marker'=:marker
                           OR (job_id=ANY(:ids) AND collector_uuid=:uid
                               AND event_type='collection_attempt_started')
                    """), {"marker": marker, "ids": jobs, "uid": uid}).rowcount
                    deleted_jobs = conn.execute(text(
                        "DELETE FROM collection_jobs WHERE job_id=ANY(:ids) AND reason=:reason"
                    ), {"ids": jobs, "reason": name}).rowcount
                    deleted_soldiers = conn.execute(text("""
                        DELETE FROM soldiers
                        WHERE soldier_id=ANY(:ids) AND current_name LIKE :prefix
                    """), {"ids": soldiers, "prefix": name + "-%"}).rowcount
                    deleted_collectors = conn.execute(text("""
                        DELETE FROM collectors
                        WHERE collector_uuid=:uid AND collector_name=:name
                    """), {"uid": uid, "name": name}).rowcount
                    counts = (deleted_jobs, deleted_events, deleted_soldiers, deleted_collectors)
                    # The production writer commits independently. If it committed
                    # and then raised, an in-memory flag is not authoritative.
                    # Exactly 1294 baseline events and at most one owned start
                    # event are valid for this test; anything else fails closed.
                    baseline = BACKGROUND_SLOTS_PER_HOUR - 2
                    valid_events = {baseline, baseline + 1} if seeded else {0}
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
