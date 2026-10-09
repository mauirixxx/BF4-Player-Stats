#!/usr/bin/env python3
"""Stage 9C expired unstarted lease reclaim diagnostic on isolated scratch only.

No HTTP. Requires --execute, exact scratch target checks, empty fixtures.
Run from repository root: python -m scripts.phase5b_stage9c_expired_reclaim_scratch
"""
from __future__ import annotations

import argparse
import os
from uuid import uuid4

from sqlalchemy import create_engine, text

from bf4ps.background_service import (
    BACKGROUND_SLOTS_PER_HOUR, _usage, claim_production_background_job,
)
from scripts.phase5b_stage9c_abort_drain_scratch import check
from scripts.phase5b_stage9c_postgres_integration import refuse_unsafe_target

MARKER = "stage9c_expired_reclaim"


def run(url: str) -> None:
    refuse_unsafe_target(url)
    engine = create_engine(
        url, pool_size=3, max_overflow=0, pool_pre_ping=True,
        connect_args={"connect_timeout": 5, "options": "-c statement_timeout=15000"},
    )
    marker = str(uuid4())
    uid = uuid4()
    name = f"{MARKER}-{marker}"
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
                "SELECT pg_advisory_xact_lock(hashtext('bf4ps:stage9c-expired-reclaim-fixture'))"
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
                    jsonb_build_object('stage9c_expired_reclaim_marker',
                                       CAST(:marker AS text),
                                       'priority_class','active','retry',false)
                FROM generate_series(1,:n)
            """), {"marker": marker, "n": BACKGROUND_SLOTS_PER_HOUR - 1})
        seeded = True

        with engine.begin() as conn:
            if _usage(conn).total != BACKGROUND_SLOTS_PER_HOUR - 1:
                raise AssertionError("incorrect baseline")
            old = claim_production_background_job(
                conn, collector_uuid=uid, resource="detailed",
                allowed_soldier_ids=soldiers,
            )
            if old is None or old.job_id != jobs[0] or old.attempt_count != 1:
                raise AssertionError(f"unexpected initial claim: {old}")
            if _usage(conn).total != BACKGROUND_SLOTS_PER_HOUR:
                raise AssertionError("initial reservation not charged")

        # Test-only clock manipulation on the single owned scratch job.
        with engine.begin() as conn:
            count = conn.execute(text("""
                UPDATE collection_jobs
                SET lease_expires_at=now()-interval '1 second', updated_at=now()
                WHERE job_id=:jid AND collector_uuid=:uid AND lease_token=:token
                  AND status='claimed'
            """), {"jid": old.job_id, "uid": uid,
                   "token": old.lease_token}).rowcount
            if count != 1:
                raise AssertionError("could not expire exact owned fixture")
            if _usage(conn).total != BACKGROUND_SLOTS_PER_HOUR:
                raise AssertionError("expired reservation unexpectedly disappeared")

        with engine.begin() as conn:
            replacement = claim_production_background_job(
                conn, collector_uuid=uid, resource="detailed",
                allowed_soldier_ids=soldiers,
            )
            usage = _usage(conn).total
            if replacement is None:
                print("OBSERVED: expired unstarted reservation blocks reclaim at 1296")
                if usage != BACKGROUND_SLOTS_PER_HOUR:
                    raise AssertionError(f"unexpected blocked usage {usage}")
                state = conn.execute(text("""
                    SELECT status,attempt_count,collector_uuid,lease_token,
                           lease_expires_at <= now() AS expired
                    FROM collection_jobs WHERE job_id=:jid
                """), {"jid": old.job_id}).mappings().one()
                if (state["status"] != "claimed"
                        or state["attempt_count"] != 1
                        or state["lease_token"] != old.lease_token
                        or not state["expired"]):
                    raise AssertionError(f"blocked state inconsistent: {state}")
                print("PASS: reproduced and fenced expired-lease capacity deadlock")
            else:
                if (replacement.job_id != old.job_id
                        or replacement.attempt_count != 2
                        or replacement.lease_token == old.lease_token
                        or usage != BACKGROUND_SLOTS_PER_HOUR):
                    raise AssertionError(
                        f"unexpected replacement: {replacement}, usage={usage}"
                    )
                print("PASS: reclaimed expired reservation at full ceiling")
        print("Battlelog requests: 0")
    finally:
        try:
            if preflight:
                with engine.begin() as conn:
                    conn.execute(text(
                        "SELECT pg_advisory_xact_lock(hashtext('bf4ps:stage9c-expired-reclaim-fixture'))"
                    ))
                    # Marker-scoped events are deleted before owned jobs.
                    deleted_events = conn.execute(text("""
                        DELETE FROM collection_events
                        WHERE metadata->>'stage9c_expired_reclaim_marker'=:marker
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
                    baseline = BACKGROUND_SLOTS_PER_HOUR - 1
                    valid_events = {baseline} if seeded else {0}
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
