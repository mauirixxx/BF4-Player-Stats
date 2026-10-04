#!/usr/bin/env python3
"""Materialize the frozen Phase 3D three-host queue without external requests."""

from __future__ import annotations

import os

from sqlalchemy import create_engine, text

from bf4ps.collection_jobs import enqueue_job

EXPECTED_REVISION = "0003_request_gates"
COHORT_IDS = (
    24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35,
    112, 113, 114, 115, 116, 117, 118, 119, 120, 121, 122, 123,
    100, 101, 102, 103, 104, 162, 163, 164, 165, 166, 167, 168,
)
EXPECTED_PLATFORM_COUNTS = {"pc": 12, "ps4": 12, "xboxone": 12}


def main() -> None:
    engine = create_engine(os.environ["BF4PS_DATABASE_URL"])

    with engine.begin() as conn:
        db = conn.execute(text("SELECT current_database()" )).scalar_one()
        recovery = conn.execute(text("SELECT pg_is_in_recovery()" )).scalar_one()
        revision = conn.execute(text("SELECT version_num FROM alembic_version" )).scalar_one()
        queue = conn.execute(text("""
            SELECT job_id, soldier_id, resource, lane, status
            FROM collection_jobs
            WHERE resource = 'detailed' AND lane = 'background'
            ORDER BY job_id
        """)).mappings().all()
        cohort = conn.execute(text("""
            SELECT s.soldier_id, s.platform, s.current_name,
                   cs.detailed_state, cs.detailed_last_attempt_at,
                   cs.detailed_last_success_at, dsc.source_fetched_at
            FROM soldiers AS s
            JOIN collection_state AS cs ON cs.soldier_id = s.soldier_id
            LEFT JOIN detailed_stats_current AS dsc ON dsc.soldier_id = s.soldier_id
            WHERE s.soldier_id = ANY(:ids)
            ORDER BY s.soldier_id
        """), {"ids": list(COHORT_IDS)}).mappings().all()
        prior_events = conn.execute(text("""
            SELECT count(*)
            FROM collection_events
            WHERE soldier_id = ANY(:ids)
              AND resource = 'detailed'
              AND lane = 'background'
              AND event_type IN ('collection_success', 'collection_failure')
        """), {"ids": list(COHORT_IDS)}).scalar_one()

        if "test" not in str(db).lower():
            raise SystemExit(f"REFUSING: not a test database: {db}")
        if recovery:
            raise SystemExit("REFUSING: database is in recovery")
        if revision != EXPECTED_REVISION:
            raise SystemExit(f"REFUSING: expected Alembic {EXPECTED_REVISION}, found {revision}")
        if queue:
            raise SystemExit(f"REFUSING: detailed/background queue is not empty: {len(queue)} row(s)")
        if prior_events:
            raise SystemExit(f"REFUSING: frozen cohort already has {prior_events} detailed/background attempt event(s)")
        if len(cohort) != len(COHORT_IDS) or {int(row['soldier_id']) for row in cohort} != set(COHORT_IDS):
            raise SystemExit("REFUSING: frozen Phase 3D cohort is incomplete")
        if any(row["detailed_state"] != "never_attempted" for row in cohort):
            raise SystemExit("REFUSING: frozen Phase 3D cohort is no longer pristine")
        if any(row["detailed_last_attempt_at"] is not None for row in cohort):
            raise SystemExit("REFUSING: frozen Phase 3D cohort has prior detailed attempts")
        if any(row["detailed_last_success_at"] is not None for row in cohort):
            raise SystemExit("REFUSING: frozen Phase 3D cohort has prior detailed success")
        if any(row["source_fetched_at"] is not None for row in cohort):
            raise SystemExit("REFUSING: frozen Phase 3D cohort already has detailed current data")

        counts = {platform: 0 for platform in EXPECTED_PLATFORM_COUNTS}
        for row in cohort:
            platform = str(row["platform"])
            if platform not in counts:
                raise SystemExit(f"REFUSING: unexpected platform in cohort: {platform}")
            counts[platform] += 1
        if counts != EXPECTED_PLATFORM_COUNTS:
            raise SystemExit(f"REFUSING: platform mix changed: {counts}")

        job_ids = []
        for soldier_id in COHORT_IDS:
            job_ids.append(enqueue_job(
                conn,
                soldier_id=soldier_id,
                resource="detailed",
                lane="background",
                priority_class="bootstrap",
                reason="phase3d_frozen_three_host_proof",
            ))

        materialized = conn.execute(text("""
            SELECT job_id, soldier_id, status, attempt_count
            FROM collection_jobs
            WHERE resource = 'detailed'
              AND lane = 'background'
            ORDER BY job_id
        """)).mappings().all()
        if len(materialized) != 36:
            raise RuntimeError(f"expected exactly 36 materialized jobs, found {len(materialized)}")
        if {int(row["soldier_id"]) for row in materialized} != set(COHORT_IDS):
            raise RuntimeError("materialized queue escaped frozen cohort")
        if any(row["status"] != "pending" or int(row["attempt_count"]) != 0 for row in materialized):
            raise RuntimeError("materialized queue is not pristine pending work")

    print("===== BF4PS PHASE 3D FROZEN QUEUE PREPARATION =====\n")
    print(f"database:       {db}")
    print(f"alembic:        {revision}")
    print(f"platform mix:   {counts}")
    print(f"jobs created:   {len(job_ids)}")
    print(f"queue boundary: {len(materialized)}/36 frozen jobs")
    print("external Battlelog requests: 0")
    print("\nPHASE 3D FROZEN QUEUE PREPARATION: PASS")
    print("The queue is now ARMED. Do not run feeders against detailed/background until Phase 3D is complete.")


if __name__ == "__main__":
    main()
