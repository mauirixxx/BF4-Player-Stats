#!/usr/bin/env python3
"""Deterministic Phase 3A two-collector PostgreSQL claim proof.

This is a database mutation/setup integration harness, not a Battlelog test.
It creates two temporary registered collectors plus two temporary detailed jobs
inside the already-frozen Phase 3A cohort, races two independent transactions
against the shared queue, validates exclusive ownership, and then rolls the
entire setup/test transaction back.

No Battlelog request is issued and no test rows are retained.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from threading import Barrier
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from bf4ps.collection_jobs import ClaimedJob, claim_next_job

EXPECTED_ALEMBIC = "0003_request_gates"
DATABASE_NAME_FRAGMENT = "test"
RESOURCE = "detailed"
LANE = "background"
LEASE_SECONDS = 120
FROZEN_COHORT = (20, 21, 22, 23, 108, 109, 110, 111, 96, 97, 98, 99)
TEST_SOLDIERS = (20, 21)

COLLECTOR_A = UUID("b2b3ef60-62e8-4d4a-91b0-41a2e2a3a001")
COLLECTOR_B = UUID("b2b3ef60-62e8-4d4a-91b0-41a2e2a3a002")
COLLECTORS = (
    (COLLECTOR_A, "phase3a-claim-proof-a"),
    (COLLECTOR_B, "phase3a-claim-proof-b"),
)
EGRESS_KEY = "phase3a-claim-proof-tcou"


@dataclass(frozen=True)
class ClaimResult:
    collector_uuid: UUID
    job: ClaimedJob | None


def _claim(engine: Engine, barrier: Barrier, collector_uuid: UUID) -> ClaimResult:
    """Open an independent transaction and compete for one shared queue row."""
    barrier.wait()
    with engine.begin() as conn:
        job = claim_next_job(
            conn,
            collector_uuid=collector_uuid,
            lane=LANE,
            resource=RESOURCE,
            lease_seconds=LEASE_SECONDS,
        )
    return ClaimResult(collector_uuid=collector_uuid, job=job)


def main() -> None:
    engine = create_engine(os.environ["BF4PS_DATABASE_URL"])

    # Safety inspection occurs before any setup mutation.
    with engine.connect() as conn:
        db = str(conn.execute(text("SELECT current_database()")).scalar_one())
        recovery = bool(conn.execute(text("SELECT pg_is_in_recovery()")).scalar_one())
        alembic = str(conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one())

        existing_queue = int(
            conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM collection_jobs
                    WHERE resource = :resource
                      AND lane = :lane
                    """
                ),
                {"resource": RESOURCE, "lane": LANE},
            ).scalar_one()
        )
        cohort_rows = conn.execute(
            text(
                """
                SELECT soldier_id, detailed_state
                FROM collection_state
                WHERE soldier_id = ANY(:cohort)
                ORDER BY soldier_id
                """
            ),
            {"cohort": list(FROZEN_COHORT)},
        ).mappings().all()
        collector_conflicts = int(
            conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM collectors
                    WHERE collector_uuid = ANY(:collector_uuids)
                       OR lower(collector_name) IN (
                           lower('phase3a-claim-proof-a'),
                           lower('phase3a-claim-proof-b')
                       )
                    """
                ),
                {"collector_uuids": [COLLECTOR_A, COLLECTOR_B]},
            ).scalar_one()
        )

    print("===== BF4PS PHASE 3A DETERMINISTIC CONCURRENT CLAIM PROOF =====")
    print()
    print("DATABASE-MUTATING INTEGRATION HARNESS")
    print("All setup/test mutations are rolled back. No Battlelog request is performed.")
    print()
    print(f"database:        {db}")
    print(f"recovery:        {recovery}")
    print(f"alembic:         {alembic}")
    print(f"resource/lane:   {RESOURCE}/{LANE}")
    print(f"test soldiers:   {list(TEST_SOLDIERS)}")
    print(f"collector A:     {COLLECTOR_A}")
    print(f"collector B:     {COLLECTOR_B}")
    print()

    if DATABASE_NAME_FRAGMENT not in db.lower():
        raise SystemExit(f"REFUSING: not a test database: {db}")
    if recovery:
        raise SystemExit("REFUSING: database is in recovery")
    if alembic != EXPECTED_ALEMBIC:
        raise SystemExit(f"REFUSING: expected Alembic {EXPECTED_ALEMBIC}, got {alembic}")
    if existing_queue != 0:
        raise SystemExit(f"REFUSING: expected empty detailed/background queue, found {existing_queue}")
    if collector_conflicts != 0:
        raise SystemExit(f"REFUSING: deterministic collector identities already exist ({collector_conflicts})")
    if len(cohort_rows) != len(FROZEN_COHORT):
        raise SystemExit("REFUSING: frozen Phase 3A cohort is incomplete")
    states = {int(row["soldier_id"]): str(row["detailed_state"]) for row in cohort_rows}
    bad_states = {sid: state for sid, state in states.items() if state != "never_attempted"}
    if bad_states:
        raise SystemExit(f"REFUSING: frozen cohort no longer pristine: {bad_states}")

    # A single outer transaction creates temporary FK-valid registry/job rows.
    # The concurrent claim connections cannot see uncommitted setup, so setup is
    # committed deliberately and then removed explicitly after the proof.  Every
    # inserted identifier is frozen and cleanup is exact/fail-closed.
    with engine.begin() as conn:
        for collector_uuid, collector_name in COLLECTORS:
            conn.execute(
                text(
                    """
                    INSERT INTO collectors (
                        collector_uuid, collector_name, hostname, lane, egress_key,
                        enabled, drained, heartbeat_state
                    ) VALUES (
                        :collector_uuid, :collector_name, 'tcou', :lane, :egress_key,
                        true, false, 'healthy'
                    )
                    """
                ),
                {
                    "collector_uuid": collector_uuid,
                    "collector_name": collector_name,
                    "lane": LANE,
                    "egress_key": EGRESS_KEY,
                },
            )
        for soldier_id in TEST_SOLDIERS:
            conn.execute(
                text(
                    """
                    INSERT INTO collection_jobs (
                        soldier_id, resource, lane, priority_class, reason,
                        status, priority_value, eligible_at
                    ) VALUES (
                        :soldier_id, :resource, :lane, 'bootstrap',
                        'phase3a_concurrent_claim_proof', 'pending', 0, now()
                    )
                    """
                ),
                {"soldier_id": soldier_id, "resource": RESOURCE, "lane": LANE},
            )

    barrier = Barrier(2)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            future_a = pool.submit(_claim, engine, barrier, COLLECTOR_A)
            future_b = pool.submit(_claim, engine, barrier, COLLECTOR_B)
            results = (future_a.result(), future_b.result())

        jobs = [result.job for result in results if result.job is not None]
        if len(jobs) != 2:
            raise RuntimeError(f"expected two successful concurrent claims, got {len(jobs)}")

        job_ids = {job.job_id for job in jobs}
        soldier_ids = {job.soldier_id for job in jobs}
        lease_tokens = {job.lease_token for job in jobs}
        owners = {job.collector_uuid for job in jobs}

        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT job_id, soldier_id, status, collector_uuid, lease_token,
                           attempt_count, lease_expires_at
                    FROM collection_jobs
                    WHERE soldier_id = ANY(:soldier_ids)
                      AND resource = :resource
                    ORDER BY job_id
                    """
                ),
                {"soldier_ids": list(TEST_SOLDIERS), "resource": RESOURCE},
            ).mappings().all()

        print("===== CONCURRENT CLAIM RESULTS =====")
        for result in sorted(results, key=lambda item: str(item.collector_uuid)):
            assert result.job is not None
            print(
                f"collector={result.collector_uuid} job={result.job.job_id} "
                f"soldier={result.job.soldier_id} attempt={result.job.attempt_count} "
                f"lease={result.job.lease_token}"
            )
        print()
        print("===== DATABASE OWNERSHIP =====")
        for row in rows:
            print(
                f"job={row['job_id']} soldier={row['soldier_id']} status={row['status']} "
                f"owner={row['collector_uuid']} attempt={row['attempt_count']} "
                f"lease={row['lease_token']} expires={row['lease_expires_at']}"
            )
        print()

        exact_jobs = len(job_ids) == 2
        exact_soldiers = soldier_ids == set(TEST_SOLDIERS)
        unique_tokens = len(lease_tokens) == 2
        both_collectors = owners == {COLLECTOR_A, COLLECTOR_B}
        db_shape = (
            len(rows) == 2
            and all(str(row["status"]) == "claimed" for row in rows)
            and {row["collector_uuid"] for row in rows} == {COLLECTOR_A, COLLECTOR_B}
            and len({row["lease_token"] for row in rows}) == 2
            and all(int(row["attempt_count"]) == 1 for row in rows)
            and all(row["lease_expires_at"] is not None for row in rows)
        )

        print("===== VALIDATION =====")
        print(f"two distinct jobs claimed:        {'PASS' if exact_jobs else 'FAIL'}")
        print(f"only frozen test soldiers:        {'PASS' if exact_soldiers else 'FAIL'}")
        print(f"both collectors obtained work:    {'PASS' if both_collectors else 'FAIL'}")
        print(f"unique lease tokens:              {'PASS' if unique_tokens else 'FAIL'}")
        print(f"database ownership shape:         {'PASS' if db_shape else 'FAIL'}")
        print("Battlelog requests:                0")

        if not all((exact_jobs, exact_soldiers, both_collectors, unique_tokens, db_shape)):
            raise RuntimeError("deterministic concurrent claim validation failed")
    finally:
        # Exact cleanup of only rows created by this harness. Jobs are removed
        # before collectors because of the collection_jobs -> collectors FK.
        with engine.begin() as conn:
            deleted_jobs = conn.execute(
                text(
                    """
                    DELETE FROM collection_jobs
                    WHERE soldier_id = ANY(:soldier_ids)
                      AND resource = :resource
                      AND reason = 'phase3a_concurrent_claim_proof'
                    """
                ),
                {"soldier_ids": list(TEST_SOLDIERS), "resource": RESOURCE},
            ).rowcount
            deleted_collectors = conn.execute(
                text("DELETE FROM collectors WHERE collector_uuid = ANY(:collector_uuids)"),
                {"collector_uuids": [COLLECTOR_A, COLLECTOR_B]},
            ).rowcount

        with engine.connect() as conn:
            remaining_jobs = int(
                conn.execute(
                    text(
                        """
                        SELECT COUNT(*) FROM collection_jobs
                        WHERE soldier_id = ANY(:soldier_ids)
                          AND resource = :resource
                          AND reason = 'phase3a_concurrent_claim_proof'
                        """
                    ),
                    {"soldier_ids": list(TEST_SOLDIERS), "resource": RESOURCE},
                ).scalar_one()
            )
            remaining_collectors = int(
                conn.execute(
                    text("SELECT COUNT(*) FROM collectors WHERE collector_uuid = ANY(:collector_uuids)"),
                    {"collector_uuids": [COLLECTOR_A, COLLECTOR_B]},
                ).scalar_one()
            )

        cleanup_ok = (
            deleted_jobs == 2
            and deleted_collectors == 2
            and remaining_jobs == 0
            and remaining_collectors == 0
        )
        print(f"exact cleanup:                    {'PASS' if cleanup_ok else 'FAIL'}")
        if not cleanup_ok:
            raise RuntimeError(
                "cleanup validation failed: "
                f"deleted_jobs={deleted_jobs} deleted_collectors={deleted_collectors} "
                f"remaining_jobs={remaining_jobs} remaining_collectors={remaining_collectors}"
            )

    print()
    print("PHASE 3A DETERMINISTIC CONCURRENT CLAIM PROOF: PASS")


if __name__ == "__main__":
    main()
