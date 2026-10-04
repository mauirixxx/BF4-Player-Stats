"""Live PostgreSQL validation of BF4PS Phase 1 queue lease semantics."""

from __future__ import annotations

import os
import threading
import time
from uuid import uuid4

from sqlalchemy import create_engine, text

from bf4ps.collection_jobs import (
    claim_next_job,
    enqueue_job,
    finalize_owned_job,
    mark_job_running,
)


def main() -> None:
    database_url = os.environ.get("BF4PS_DATABASE_URL")
    if not database_url:
        raise SystemExit("BF4PS_DATABASE_URL is required")

    engine = create_engine(database_url)

    # ------------------------------------------------------------
    # SAFETY + TEST SUBJECT
    # ------------------------------------------------------------

    with engine.begin() as conn:
        database_name = conn.execute(
            text("SELECT current_database()")
        ).scalar_one()

        if "test" not in database_name.lower():
            raise SystemExit(
                "REFUSING TO RUN: destination database does not contain "
                f"'test': {database_name}"
            )

        soldier = conn.execute(
            text("""
                SELECT
                    soldier_id,
                    persona_id,
                    platform,
                    current_name
                FROM soldiers
                ORDER BY soldier_id
                LIMIT 1
            """)
        ).mappings().one()

        soldier_id = soldier["soldier_id"]

        # Keep this harness isolated from any pre-existing queue work.
        existing_jobs = conn.execute(
            text("""
                SELECT COUNT(*)
                FROM collection_jobs
                WHERE soldier_id = :soldier_id
                  AND resource = 'detailed'
            """),
            {"soldier_id": soldier_id},
        ).scalar_one()

        if existing_jobs:
            raise SystemExit(
                f"REFUSING TO RUN: soldier {soldier_id} already has "
                f"{existing_jobs} detailed collection job(s)"
            )

        job_id = enqueue_job(
            conn,
            soldier_id=soldier_id,
            resource="detailed",
            reason="phase1_queue_race",
        )

    collector_a = uuid4()
    collector_b = uuid4()

    # Register the two temporary collectors. collection_jobs.collector_uuid
    # is deliberately FK-constrained to this registry.
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO collectors (
                    collector_uuid,
                    collector_name,
                    hostname,
                    lane,
                    egress_key,
                    enabled,
                    drained,
                    heartbeat_state
                )
                VALUES
                    (
                        :collector_a,
                        'phase1-race-a',
                        'tcou',
                        'background',
                        'phase1-test-a',
                        true,
                        false,
                        'unknown'
                    ),
                    (
                        :collector_b,
                        'phase1-race-b',
                        'tcou',
                        'background',
                        'phase1-test-b',
                        true,
                        false,
                        'unknown'
                    )
            """),
            {
                "collector_a": collector_a,
                "collector_b": collector_b,
            },
        )

    print("===== BF4PS PHASE 1 QUEUE RACE =====")
    print()
    print(f"database:    {database_name}")
    print(f"soldier_id:  {soldier_id}")
    print(f"persona_id:  {soldier['persona_id']}")
    print(f"platform:    {soldier['platform']}")
    print(f"name:        {soldier['current_name']}")
    print(f"job_id:      {job_id}")
    print(f"collector A: {collector_a}")
    print(f"collector B: {collector_b}")

    # ------------------------------------------------------------
    # SIMULTANEOUS CLAIM
    # ------------------------------------------------------------

    barrier = threading.Barrier(2)

    results = {}
    errors = []

    def racer(label, collector_uuid):
        try:
            with engine.begin() as conn:
                barrier.wait(timeout=10)

                results[label] = claim_next_job(
                    conn,
                    collector_uuid=collector_uuid,
                    lease_seconds=2,
                )

        except BaseException as exc:
            errors.append(exc)

    threads = [
        threading.Thread(
            target=racer,
            args=("A", collector_a),
            daemon=True,
        ),
        threading.Thread(
            target=racer,
            args=("B", collector_b),
            daemon=True,
        ),
    ]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join(timeout=15)

    if errors:
        raise errors[0]

    if any(thread.is_alive() for thread in threads):
        raise RuntimeError("race threads did not finish")

    winners = [
        (label, job)
        for label, job in results.items()
        if job is not None
    ]

    losers = [
        (label, job)
        for label, job in results.items()
        if job is None
    ]

    print()
    print("===== SIMULTANEOUS CLAIM =====")
    print(f"winners: {len(winners)}")
    print(f"losers:  {len(losers)}")

    if len(winners) != 1 or len(losers) != 1:
        raise AssertionError(
            "expected exactly one winner and one loser; "
            f"results={results!r}"
        )

    winner_label, winner = winners[0]

    print(f"winner:  collector {winner_label}")
    print(f"token:   {winner.lease_token}")
    print(f"attempt: {winner.attempt_count}")

    # ------------------------------------------------------------
    # CLAIMED -> RUNNING
    # ------------------------------------------------------------

    with engine.begin() as conn:
        running_ok = mark_job_running(conn, winner)

    print()
    print("===== CLAIMED -> RUNNING =====")
    print(f"accepted: {running_ok}")

    if not running_ok:
        raise AssertionError(
            "winning collector could not move claimed -> running"
        )

    # ------------------------------------------------------------
    # LEASE EXPIRY + RECLAIM
    # ------------------------------------------------------------

    print()
    print("===== LEASE EXPIRY / RECLAIM =====")
    print("waiting for 2-second lease to expire...")

    time.sleep(2.5)

    if winner.collector_uuid == collector_a:
        reclaimer_uuid = collector_b
        reclaimer_label = "B"
    else:
        reclaimer_uuid = collector_a
        reclaimer_label = "A"

    with engine.begin() as conn:
        reclaimed = claim_next_job(
            conn,
            collector_uuid=reclaimer_uuid,
            lease_seconds=30,
        )

    if reclaimed is None:
        raise AssertionError(
            "expired running job was not reclaimable"
        )

    if reclaimed.job_id != winner.job_id:
        raise AssertionError(
            "reclaimer claimed a different job"
        )

    if reclaimed.lease_token == winner.lease_token:
        raise AssertionError(
            "reclaim did not rotate the fencing token"
        )

    print(f"reclaimed by: collector {reclaimer_label}")
    print(f"old token:    {winner.lease_token}")
    print(f"new token:    {reclaimed.lease_token}")
    print(f"attempt:      {reclaimed.attempt_count}")

    # ------------------------------------------------------------
    # STALE OWNER FENCING
    # ------------------------------------------------------------

    with engine.begin() as conn:
        stale_finalize = finalize_owned_job(
            conn,
            winner,
        )

    print()
    print("===== STALE OWNER FENCING =====")
    print(
        "stale winner finalize accepted: "
        f"{stale_finalize}"
    )

    if stale_finalize:
        raise AssertionError(
            "STALE OWNER WAS ALLOWED TO FINALIZE"
        )

    # ------------------------------------------------------------
    # CURRENT OWNER FINALIZATION
    # ------------------------------------------------------------

    with engine.begin() as conn:
        running_ok = mark_job_running(
            conn,
            reclaimed,
        )

        if not running_ok:
            raise AssertionError(
                "reclaimer could not move claimed -> running"
            )

        current_finalize = finalize_owned_job(
            conn,
            reclaimed,
        )

    print()
    print("===== CURRENT OWNER =====")
    print(
        "current owner finalize accepted: "
        f"{current_finalize}"
    )

    if not current_finalize:
        raise AssertionError(
            "current owner could not finalize"
        )

    # ------------------------------------------------------------
    # FINAL DATABASE STATE
    # ------------------------------------------------------------

    with engine.begin() as conn:
        remaining = conn.execute(
            text("""
                SELECT COUNT(*)
                FROM collection_jobs
                WHERE job_id = :job_id
            """),
            {"job_id": job_id},
        ).scalar_one()

        if remaining != 0:
            raise AssertionError(
                "finalized queue row still exists"
            )

        deleted_collectors = conn.execute(
            text("""
                DELETE FROM collectors
                WHERE collector_uuid IN (
                    :collector_a,
                    :collector_b
                )
            """),
            {
                "collector_a": collector_a,
                "collector_b": collector_b,
            },
        ).rowcount

    print()
    print("===== FINAL STATE =====")
    print(f"queue row remaining:       {remaining}")
    print(f"test collectors removed:   {deleted_collectors}")

    if deleted_collectors != 2:
        raise AssertionError(
            "expected to remove exactly two test collectors"
        )

    print()
    print("PHASE 1 QUEUE RACE: PASS")


if __name__ == "__main__":
    main()
