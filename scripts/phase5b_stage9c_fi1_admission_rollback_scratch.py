#!/usr/bin/env python3
"""FI-1: rolled-back production admission releases its reservation (scratch only).

No HTTP. Requires --execute, allowlisted empty Stage 9C PostgreSQL scratch DB.
"""
from __future__ import annotations

import argparse
import os
from uuid import uuid4

from sqlalchemy import create_engine, text

from bf4ps.background_service import BACKGROUND_SLOTS_PER_HOUR, _usage, claim_production_background_job
from scripts.phase5b_stage9c_abort_drain_scratch import check
from scripts.phase5b_stage9c_postgres_integration import refuse_unsafe_target

MARKER = "stage9c_fi1_rollback"
TABLES = ("collectors", "soldiers", "collection_jobs", "collection_events", "stage9c_supervision_runs")


def run(url: str) -> None:
    refuse_unsafe_target(url)
    engine = create_engine(
        url, pool_size=3, max_overflow=0, pool_pre_ping=True,
        connect_args={"connect_timeout": 5, "options": "-c statement_timeout=15000"},
    )
    marker = str(uuid4())
    collectors, soldiers, jobs = [], [], []
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
            conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('bf4ps:stage9c-fi1-fixture'))"))
            for table in TABLES:
                if conn.execute(text(f"SELECT count(*) FROM public.{table}")).scalar_one():
                    raise RuntimeError(f"REFUSING concurrently populated {table}")
            for i, resource in enumerate(("weapons", "vehicles")):
                uid = uuid4()
                collectors.append(uid)
                name = f"{MARKER}-{marker}-{i}"
                conn.execute(text("""
                    INSERT INTO collectors
                        (collector_uuid,collector_name,hostname,lane,egress_key,
                         enabled,drained,heartbeat_state)
                    VALUES (:uid,:name,'stage9c-scratch','background',:name,true,false,'healthy')
                """), {"uid": uid, "name": name})
                sid = int(conn.execute(text("""
                    INSERT INTO soldiers
                        (persona_id,platform,current_name,first_seen_at,last_seen_at)
                    VALUES (:persona,'pc',:name,now(),now()) RETURNING soldier_id
                """), {"persona": 800000000000 + i + int(uid.int % 10000000),
                         "name": name}).scalar_one())
                soldiers.append(sid)
                jid = int(conn.execute(text("""
                    INSERT INTO collection_jobs
                        (soldier_id,resource,lane,priority_class,reason,
                         status,priority_value,eligible_at)
                    VALUES (:sid,:resource,'background','active',:reason,
                            'pending',0,now()) RETURNING job_id
                """), {"sid": sid, "resource": resource, "reason": f"{MARKER}-{marker}"}).scalar_one())
                jobs.append(jid)
            conn.execute(text("""
                INSERT INTO collection_events
                    (resource,lane,event_type,attempt_number,metadata)
                SELECT 'detailed','background','collection_attempt_started',1,
                    jsonb_build_object('stage9c_fi1_marker',CAST(:marker AS text),
                                       'priority_class','active','retry',false)
                FROM generate_series(1,:n)
            """), {"marker": marker, "n": BACKGROUND_SLOTS_PER_HOUR - 1})
        seeded = True

        # Explicit rollback of a real admission transaction, not a mock claim.
        with engine.connect() as first:
            transaction = first.begin()
            try:
                if _usage(first).total != BACKGROUND_SLOTS_PER_HOUR - 1:
                    raise AssertionError("incorrect baseline")
                rolled_back = claim_production_background_job(
                    first, collector_uuid=collectors[0], resource="weapons",
                    allowed_soldier_ids=[soldiers[0]],
                )
                if rolled_back is None or rolled_back.job_id != jobs[0]:
                    raise AssertionError(f"initial claim failed: {rolled_back}")
                if _usage(first).total != BACKGROUND_SLOTS_PER_HOUR:
                    raise AssertionError("uncommitted reservation not charged in owner transaction")
                with engine.connect() as observer:
                    if _usage(observer).total != BACKGROUND_SLOTS_PER_HOUR - 1:
                        raise AssertionError("uncommitted reservation visible to independent connection")
                    observer.rollback()
            finally:
                transaction.rollback()

        with engine.begin() as conn:
            if _usage(conn).total != BACKGROUND_SLOTS_PER_HOUR - 1:
                raise AssertionError("rolled-back claim still charged")
            state = conn.execute(text("""
                SELECT status,attempt_count,collector_uuid,lease_token,lease_expires_at
                FROM collection_jobs WHERE job_id=:jid
            """), {"jid": jobs[0]}).mappings().one()
            if (state["status"] != "pending" or state["attempt_count"] != 0
                    or state["collector_uuid"] is not None or state["lease_token"] is not None
                    or state["lease_expires_at"] is not None):
                raise AssertionError(f"rolled-back job ownership persisted: {state}")
            if conn.execute(text("""
                SELECT count(*) FROM collection_events WHERE job_id=:jid
                  AND event_type='collection_attempt_started'
            """), {"jid": jobs[0]}).scalar_one():
                raise AssertionError("rolled-back claim produced a start event")
        print("PASS: rolled-back claim leaves no committed reservation or start event")

        # A second transaction must acquire the advisory admission lock and
        # use the released final slot. The original job stays pending.
        with engine.begin() as conn:
            winner = claim_production_background_job(
                conn, collector_uuid=collectors[1], resource="vehicles",
                allowed_soldier_ids=[soldiers[1]],
            )
            if winner is None or winner.job_id != jobs[1]:
                raise AssertionError(f"final slot not reusable after rollback: {winner}")
            if _usage(conn).total != BACKGROUND_SLOTS_PER_HOUR:
                raise AssertionError("replacement final slot not charged")
        with engine.begin() as conn:
            if _usage(conn).total != BACKGROUND_SLOTS_PER_HOUR:
                raise AssertionError("replacement claim not committed")
            if claim_production_background_job(
                conn, collector_uuid=collectors[0], resource="weapons",
                allowed_soldier_ids=[soldiers[0]],
            ) is not None:
                raise AssertionError("admitted 1297th slot")
        print("PASS: independent collector reuses slot 1296; slot 1297 denied")
        print("Battlelog requests: 0")
    finally:
        try:
            if preflight:
                with engine.begin() as conn:
                    conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('bf4ps:stage9c-fi1-fixture'))"))
                    deleted_jobs = conn.execute(text("""
                        DELETE FROM collection_jobs
                        WHERE job_id=ANY(:ids) AND reason=:reason
                    """), {"ids": jobs, "reason": f"{MARKER}-{marker}"}).rowcount
                    deleted_events = conn.execute(text("""
                        DELETE FROM collection_events
                        WHERE metadata->>'stage9c_fi1_marker'=:marker
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
