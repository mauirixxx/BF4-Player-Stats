#!/usr/bin/env python3
"""Deterministic Phase 3B lease expiry/reclamation/fencing proof.

This database-mutating integration harness exercises the real BF4PS queue
ownership primitives with a deliberately short lease. It performs no Battlelog
requests and cleans up only its frozen test rows.
"""

from __future__ import annotations

import os
import time
from uuid import UUID

from sqlalchemy import create_engine, text

from bf4ps.collection_jobs import (
    ClaimedJob,
    claim_next_job,
    finalize_owned_job,
    mark_job_running,
    release_for_retry,
    renew_lease,
)

EXPECTED_ALEMBIC = "0003_request_gates"
DATABASE_NAME_FRAGMENT = "test"
RESOURCE = "detailed"
LANE = "background"
TEST_SOLDIER = 24
LEASE_SECONDS = 2
EXPIRY_MARGIN_SECONDS = 0.35
REASON = "phase3b_lease_fencing_proof"

COLLECTOR_A = UUID("b2b3ef60-62e8-4d4a-91b0-41a2e2a3b001")
COLLECTOR_B = UUID("b2b3ef60-62e8-4d4a-91b0-41a2e2a3b002")
COLLECTORS = (
    (COLLECTOR_A, "phase3b-fencing-a"),
    (COLLECTOR_B, "phase3b-fencing-b"),
)
EGRESS_KEY = "phase3b-fencing-tcou"


def _claim(engine, collector_uuid: UUID) -> ClaimedJob | None:
    with engine.begin() as conn:
        return claim_next_job(
            conn,
            collector_uuid=collector_uuid,
            lane=LANE,
            resource=RESOURCE,
            lease_seconds=LEASE_SECONDS,
        )


def _job_row(engine, job_id: int):
    with engine.connect() as conn:
        return conn.execute(
            text(
                """
                SELECT job_id, soldier_id, resource, lane, status, attempt_count,
                       collector_uuid, lease_token, claimed_at, started_at,
                       lease_expires_at, reason
                FROM collection_jobs
                WHERE job_id = :job_id
                """
            ),
            {"job_id": job_id},
        ).mappings().one_or_none()


def main() -> None:
    engine = create_engine(os.environ["BF4PS_DATABASE_URL"])

    with engine.connect() as conn:
        db = str(conn.execute(text("SELECT current_database()")).scalar_one())
        recovery = bool(conn.execute(text("SELECT pg_is_in_recovery()")).scalar_one())
        alembic = str(conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one())
        existing_queue = int(
            conn.execute(
                text(
                    """
                    SELECT COUNT(*) FROM collection_jobs
                    WHERE resource = :resource AND lane = :lane
                    """
                ),
                {"resource": RESOURCE, "lane": LANE},
            ).scalar_one()
        )
        soldier = conn.execute(
            text(
                """
                SELECT s.soldier_id, s.platform, s.current_name, cs.detailed_state
                FROM soldiers AS s
                JOIN collection_state AS cs ON cs.soldier_id = s.soldier_id
                WHERE s.soldier_id = :soldier_id
                """
            ),
            {"soldier_id": TEST_SOLDIER},
        ).mappings().one_or_none()
        collector_conflicts = int(
            conn.execute(
                text(
                    """
                    SELECT COUNT(*) FROM collectors
                    WHERE collector_uuid = ANY(:collector_uuids)
                       OR lower(collector_name) IN (
                           lower('phase3b-fencing-a'), lower('phase3b-fencing-b')
                       )
                    """
                ),
                {"collector_uuids": [COLLECTOR_A, COLLECTOR_B]},
            ).scalar_one()
        )

    print("===== BF4PS PHASE 3B LEASE EXPIRY / RECLAMATION / FENCING PROOF =====")
    print()
    print("DATABASE-MUTATING INTEGRATION HARNESS")
    print("Exact test rows are cleaned up. No Battlelog request is performed.")
    print()
    print(f"database:        {db}")
    print(f"recovery:        {recovery}")
    print(f"alembic:         {alembic}")
    print(f"resource/lane:   {RESOURCE}/{LANE}")
    print(f"test soldier:    {TEST_SOLDIER}")
    print(f"short lease:     {LEASE_SECONDS}s")
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
    if soldier is None:
        raise SystemExit(f"REFUSING: frozen test soldier {TEST_SOLDIER} does not exist")
    if str(soldier["detailed_state"]) != "never_attempted":
        raise SystemExit(
            f"REFUSING: soldier {TEST_SOLDIER} detailed_state is {soldier['detailed_state']}, expected never_attempted"
        )

    job_id: int | None = None
    try:
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
            job_id = int(
                conn.execute(
                    text(
                        """
                        INSERT INTO collection_jobs (
                            soldier_id, resource, lane, priority_class, reason,
                            status, priority_value, eligible_at
                        ) VALUES (
                            :soldier_id, :resource, :lane, 'bootstrap', :reason,
                            'pending', 0, now()
                        )
                        RETURNING job_id
                        """
                    ),
                    {
                        "soldier_id": TEST_SOLDIER,
                        "resource": RESOURCE,
                        "lane": LANE,
                        "reason": REASON,
                    },
                ).scalar_one()
            )

        claim_a = _claim(engine, COLLECTOR_A)
        if claim_a is None:
            raise RuntimeError("collector A failed to claim frozen test job")
        if claim_a.job_id != job_id or claim_a.soldier_id != TEST_SOLDIER:
            raise RuntimeError(f"collector A claimed unexpected work: {claim_a}")
        row_a = _job_row(engine, job_id)

        claim_b_early = _claim(engine, COLLECTOR_B)
        early_blocked = claim_b_early is None

        print("===== INITIAL OWNERSHIP =====")
        print(
            f"A owns job={claim_a.job_id} soldier={claim_a.soldier_id} "
            f"attempt={claim_a.attempt_count} token={claim_a.lease_token}"
        )
        print(f"database status={row_a['status']} expires={row_a['lease_expires_at']}")
        print(f"B claim before expiry: {'BLOCKED' if early_blocked else 'UNEXPECTED CLAIM'}")
        print()
        if not early_blocked:
            raise RuntimeError(f"collector B claimed job before A lease expiry: {claim_b_early}")

        time.sleep(LEASE_SECONDS + EXPIRY_MARGIN_SECONDS)
        claim_b = _claim(engine, COLLECTOR_B)
        if claim_b is None:
            raise RuntimeError("collector B failed to reclaim expired job")
        row_b = _job_row(engine, job_id)

        same_job = claim_b.job_id == claim_a.job_id == job_id
        attempt_incremented = claim_a.attempt_count == 1 and claim_b.attempt_count == 2
        token_rotated = claim_b.lease_token != claim_a.lease_token
        ownership_transferred = (
            row_b is not None
            and row_b["collector_uuid"] == COLLECTOR_B
            and row_b["lease_token"] == claim_b.lease_token
            and str(row_b["status"]) == "claimed"
            and int(row_b["attempt_count"]) == 2
        )

        print("===== POST-EXPIRY RECLAMATION =====")
        print(
            f"B reclaimed job={claim_b.job_id} soldier={claim_b.soldier_id} "
            f"attempt={claim_b.attempt_count} token={claim_b.lease_token}"
        )
        print(f"same logical job:      {'PASS' if same_job else 'FAIL'}")
        print(f"attempt 1 -> 2:        {'PASS' if attempt_incremented else 'FAIL'}")
        print(f"token A != token B:    {'PASS' if token_rotated else 'FAIL'}")
        print(f"ownership transferred: {'PASS' if ownership_transferred else 'FAIL'}")
        print()

        # Attack B's current ownership using A's retained stale ClaimedJob.
        with engine.begin() as conn:
            stale_mark_running = mark_job_running(conn, claim_a)
        with engine.begin() as conn:
            stale_renew = renew_lease(conn, claim_a, lease_seconds=LEASE_SECONDS)
        with engine.begin() as conn:
            stale_release = release_for_retry(conn, claim_a, retry_after_seconds=0)
        with engine.begin() as conn:
            stale_finalize = finalize_owned_job(conn, claim_a)

        row_after_attacks = _job_row(engine, job_id)
        stale_rejected = not any((stale_mark_running, stale_renew, stale_release, stale_finalize))
        b_ownership_intact = (
            row_after_attacks is not None
            and row_after_attacks["collector_uuid"] == COLLECTOR_B
            and row_after_attacks["lease_token"] == claim_b.lease_token
            and str(row_after_attacks["status"]) == "claimed"
            and int(row_after_attacks["attempt_count"]) == 2
        )

        print("===== STALE OWNER ATTACKS =====")
        print(f"A mark B job running:  {'REJECTED' if not stale_mark_running else 'ACCEPTED'}")
        print(f"A renew B lease:       {'REJECTED' if not stale_renew else 'ACCEPTED'}")
        print(f"A release B job:       {'REJECTED' if not stale_release else 'ACCEPTED'}")
        print(f"A finalize B job:      {'REJECTED' if not stale_finalize else 'ACCEPTED'}")
        print(f"B ownership intact:    {'PASS' if b_ownership_intact else 'FAIL'}")
        print()

        with engine.begin() as conn:
            b_running = mark_job_running(conn, claim_b)
        row_running = _job_row(engine, job_id)
        with engine.begin() as conn:
            b_finalized = finalize_owned_job(conn, claim_b)
        row_final = _job_row(engine, job_id)

        b_can_continue = (
            b_running
            and row_running is not None
            and str(row_running["status"]) == "running"
            and row_running["collector_uuid"] == COLLECTOR_B
            and row_running["lease_token"] == claim_b.lease_token
        )
        b_can_finalize = b_finalized and row_final is None

        checks = {
            "A initially owns token A": row_a is not None and row_a["lease_token"] == claim_a.lease_token,
            "B blocked before expiry": early_blocked,
            "B reclaims same job": same_job and ownership_transferred,
            "reclaim increments attempt": attempt_incremented,
            "reclaim rotates token": token_rotated,
            "all stale A mutations rejected": stale_rejected,
            "B ownership survives stale attacks": b_ownership_intact,
            "B can mark reclaimed job running": b_can_continue,
            "B can finalize current ownership": b_can_finalize,
        }

        print("===== FINAL VALIDATION =====")
        for label, passed in checks.items():
            print(f"{label:<38} {'PASS' if passed else 'FAIL'}")
        print("Battlelog requests:                    0")

        if not all(checks.values()):
            raise RuntimeError("Phase 3B lease fencing validation failed")

    finally:
        # The current owner normally finalized the job. This exact delete only
        # removes the harness job if an earlier assertion failed.
        with engine.begin() as conn:
            cleanup_jobs = conn.execute(
                text(
                    """
                    DELETE FROM collection_jobs
                    WHERE soldier_id = :soldier_id
                      AND resource = :resource
                      AND reason = :reason
                    """
                ),
                {"soldier_id": TEST_SOLDIER, "resource": RESOURCE, "reason": REASON},
            ).rowcount
            cleanup_collectors = conn.execute(
                text("DELETE FROM collectors WHERE collector_uuid = ANY(:collector_uuids)"),
                {"collector_uuids": [COLLECTOR_A, COLLECTOR_B]},
            ).rowcount

        with engine.connect() as conn:
            remaining_jobs = int(
                conn.execute(
                    text(
                        """
                        SELECT COUNT(*) FROM collection_jobs
                        WHERE soldier_id = :soldier_id
                          AND resource = :resource
                          AND reason = :reason
                        """
                    ),
                    {"soldier_id": TEST_SOLDIER, "resource": RESOURCE, "reason": REASON},
                ).scalar_one()
            )
            remaining_collectors = int(
                conn.execute(
                    text("SELECT COUNT(*) FROM collectors WHERE collector_uuid = ANY(:collector_uuids)"),
                    {"collector_uuids": [COLLECTOR_A, COLLECTOR_B]},
                ).scalar_one()
            )

        cleanup_ok = remaining_jobs == 0 and remaining_collectors == 0 and cleanup_collectors == 2
        print(f"exact cleanup:                         {'PASS' if cleanup_ok else 'FAIL'}")
        if not cleanup_ok:
            raise RuntimeError(
                "cleanup validation failed: "
                f"fallback_deleted_jobs={cleanup_jobs} deleted_collectors={cleanup_collectors} "
                f"remaining_jobs={remaining_jobs} remaining_collectors={remaining_collectors}"
            )

    print()
    print("BF4PS PHASE 3B LEASE EXPIRY / RECLAMATION / FENCING PROOF: PASS")


if __name__ == "__main__":
    main()
