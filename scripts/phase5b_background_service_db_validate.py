#!/usr/bin/env python3
"""Rollback-only Phase 5B background-service SQL validation.

No Battlelog requests are made. The harness requires four explicit existing
soldiers in bf4_playerstats_test, creates a transaction-local collector and
queue/event fixtures, exercises production background admission, and always
rolls the entire transaction back.
"""
from __future__ import annotations

import argparse
from uuid import uuid4

from sqlalchemy import text

from bf4ps.background_service import (
    BACKGROUND_SLOTS_PER_HOUR,
    BOOTSTRAP_SLOTS,
    RECOVERY_SLOTS,
    claim_production_background_job,
)
from bf4ps.db import make_engine

EXPECTED_DATABASE = "bf4_playerstats_test"
EXPECTED_REVISION = "0003_request_gates"


def _assert_target(conn, soldier_ids: list[int]) -> None:
    database = conn.execute(text("SELECT current_database()")).scalar_one()
    if database != EXPECTED_DATABASE:
        raise RuntimeError(f"refusing database {database!r}; expected {EXPECTED_DATABASE!r}")
    revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    if revision != EXPECTED_REVISION:
        raise RuntimeError(f"refusing Alembic revision {revision!r}; expected {EXPECTED_REVISION!r}")

    rows = conn.execute(
        text(
            """
            SELECT soldier_id
            FROM soldiers
            WHERE soldier_id = ANY(:soldier_ids)
            FOR UPDATE
            """
        ),
        {"soldier_ids": soldier_ids},
    ).scalars().all()
    if set(rows) != set(soldier_ids):
        missing = sorted(set(soldier_ids) - set(rows))
        raise RuntimeError(f"missing requested soldier IDs: {missing}")

    owned = conn.execute(
        text(
            """
            SELECT soldier_id, resource, status
            FROM collection_jobs
            WHERE soldier_id = ANY(:soldier_ids)
              AND status IN ('claimed', 'running')
            """
        ),
        {"soldier_ids": soldier_ids},
    ).mappings().all()
    if owned:
        raise RuntimeError(f"requested soldiers have owned jobs; choose idle soldiers: {owned}")


def _register_test_collector(conn):
    collector_uuid = uuid4()
    conn.execute(
        text(
            """
            INSERT INTO collectors
                (collector_uuid, collector_name, hostname, lane, egress_key,
                 enabled, drained, heartbeat_state)
            VALUES
                (:uuid, :name, 'phase5b-db-validate', 'background', :egress,
                 true, false, 'healthy')
            """
        ),
        {
            "uuid": collector_uuid,
            "name": f"phase5b-db-validate-{collector_uuid}",
            "egress": f"phase5b-db-validate-{collector_uuid}",
        },
    )
    return collector_uuid


def _clear_jobs(conn, soldier_ids: list[int]) -> None:
    conn.execute(
        text("DELETE FROM collection_jobs WHERE soldier_id = ANY(:soldier_ids)"),
        {"soldier_ids": soldier_ids},
    )


def _enqueue(conn, soldier_id: int, *, priority_class: str, retry: bool = False, lane: str = "background") -> int:
    row = conn.execute(
        text(
            """
            INSERT INTO collection_jobs
                (soldier_id, resource, lane, priority_class, reason, status,
                 priority_value, eligible_at, last_error_class, last_error_at)
            VALUES
                (:soldier_id, 'detailed', :lane, :priority_class,
                 'phase5b_db_validate', 'pending', 0, now(),
                 CASE WHEN :retry THEN 'validation_retry' ELSE NULL END,
                 CASE WHEN :retry THEN now() ELSE NULL END)
            RETURNING job_id
            """
        ),
        {
            "soldier_id": soldier_id,
            "lane": lane,
            "priority_class": priority_class,
            "retry": retry,
        },
    ).scalar_one()
    return int(row)


def _seed_attempt_usage(conn, *, count: int, priority_class: str, retry: bool = False) -> None:
    if count <= 0:
        return
    conn.execute(
        text(
            """
            INSERT INTO collection_events
                (resource, lane, event_type, attempt_number, metadata)
            SELECT
                'detailed', 'background', 'collection_attempt_started', 1,
                jsonb_build_object(
                    'physical_request', true,
                    'priority_class', CAST(:priority_class AS text),
                    'retry', CAST(:retry AS boolean)
                )
            FROM generate_series(1, CAST(:count AS integer))
            """
        ),
        {"count": count, "priority_class": priority_class, "retry": retry},
    )


def _release_claim(conn, job_id: int) -> None:
    conn.execute(
        text(
            """
            UPDATE collection_jobs
            SET status = 'pending', collector_uuid = NULL, lease_token = NULL,
                claimed_at = NULL, started_at = NULL, lease_expires_at = NULL
            WHERE job_id = :job_id
            """
        ),
        {"job_id": job_id},
    )


def run_validation(soldier_ids: list[int]) -> None:
    engine = make_engine()
    conn = engine.connect()
    tx = conn.begin()
    try:
        _assert_target(conn, soldier_ids)
        collector_uuid = _register_test_collector(conn)
        _clear_jobs(conn, soldier_ids)

        # Isolate this transaction from real recent attempt history so each
        # scenario starts from a deterministic service-usage baseline.
        conn.execute(
            text(
                """
                UPDATE collection_events
                SET occurred_at = now() - interval '2 hours'
                WHERE lane = 'background'
                  AND event_type = 'collection_attempt_started'
                  AND occurred_at >= now() - interval '1 hour'
                """
            )
        )

        # 1. Interactive precedence: any eligible interactive work prevents a
        # new production background claim.
        _enqueue(conn, soldier_ids[0], priority_class="interactive", lane="interactive")
        _enqueue(conn, soldier_ids[1], priority_class="active")
        assert claim_production_background_job(
            conn, collector_uuid=collector_uuid, resource="detailed"
        ) is None
        _clear_jobs(conn, soldier_ids)

        # 2. Bootstrap floor: while below its floor and bootstrap is pending,
        # bootstrap wins over competing active work.
        active_id = _enqueue(conn, soldier_ids[0], priority_class="active")
        bootstrap_id = _enqueue(conn, soldier_ids[1], priority_class="bootstrap")
        job = claim_production_background_job(
            conn, collector_uuid=collector_uuid, resource="detailed"
        )
        assert job is not None and job.job_id == bootstrap_id
        _release_claim(conn, job.job_id)
        _clear_jobs(conn, soldier_ids)

        # 3. Recovery floor: once bootstrap's floor is represented, retry work
        # wins while recovery remains below its reservation.
        _seed_attempt_usage(conn, count=BOOTSTRAP_SLOTS, priority_class="bootstrap")
        _enqueue(conn, soldier_ids[0], priority_class="active")
        retry_id = _enqueue(conn, soldier_ids[1], priority_class="active", retry=True)
        job = claim_production_background_job(
            conn, collector_uuid=collector_uuid, resource="detailed"
        )
        assert job is not None and job.job_id == retry_id
        _release_claim(conn, job.job_id)
        _clear_jobs(conn, soldier_ids)

        # 4. Borrowing: after bootstrap + recovery floors are represented, an
        # active job can consume an otherwise unused slot.
        _seed_attempt_usage(
            conn, count=RECOVERY_SLOTS, priority_class="active", retry=True
        )
        active_id = _enqueue(conn, soldier_ids[0], priority_class="active")
        job = claim_production_background_job(
            conn, collector_uuid=collector_uuid, resource="detailed"
        )
        assert job is not None and job.job_id == active_id
        _release_claim(conn, job.job_id)
        _clear_jobs(conn, soldier_ids)

        # 5. Aggregate ceiling: fill the remaining rolling-hour budget and
        # prove no additional background job can be admitted.
        used = BOOTSTRAP_SLOTS + RECOVERY_SLOTS
        _seed_attempt_usage(
            conn,
            count=BACKGROUND_SLOTS_PER_HOUR - used,
            priority_class="active",
        )
        _enqueue(conn, soldier_ids[0], priority_class="active")
        assert claim_production_background_job(
            conn, collector_uuid=collector_uuid, resource="detailed"
        ) is None

        print("PASS: Phase 5B rollback-only background-service DB validation")
        print(f"  soldiers: {', '.join(str(v) for v in soldier_ids)}")
        print("  interactive precedence: PASS")
        print("  bootstrap starvation floor: PASS")
        print("  retry/recovery starvation floor: PASS")
        print("  unused reservation borrowing: PASS")
        print(f"  aggregate rolling-hour ceiling ({BACKGROUND_SLOTS_PER_HOUR}): PASS")
        print("  Battlelog requests: 0")
        print("  committed database writes: 0 (transaction rolled back)")
    finally:
        if tx.is_active:
            tx.rollback()
        conn.close()
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--soldier-id", type=int, action="append", required=True)
    args = parser.parse_args()
    soldier_ids = list(dict.fromkeys(args.soldier_id))
    if len(soldier_ids) != 4 or any(value <= 0 for value in soldier_ids):
        parser.error("provide exactly four distinct positive --soldier-id values")
    run_validation(soldier_ids)


if __name__ == "__main__":
    main()
