#!/usr/bin/env python3
"""Read-only launch preflight for Phase 5B Step 6 bounded live workers."""
from __future__ import annotations

import os
from urllib.parse import urlsplit

from sqlalchemy import create_engine, text

from bf4ps.phase5b_step6_cohort import (
    EXPECTED_DATABASE,
    EXPECTED_REVISION,
    FROZEN_UUIDS,
    GLOBAL_ATTEMPT_CEILING,
    HOSTS,
    RESOURCES,
    RUN_MARKER_EVENT_TYPE,
    RUN_NUMBER,
    SOLDIER_IDS,
)


def main() -> int:
    url = os.environ.get("BF4PS_DATABASE_URL")
    parsed = urlsplit(url or "")
    if not url or parsed.path.lstrip("/") != EXPECTED_DATABASE:
        raise SystemExit("REFUSING: wrong or missing BF4PS_DATABASE_URL")

    engine = create_engine(url, pool_pre_ping=True)
    with engine.connect() as conn:
        db = conn.execute(text("SELECT current_database()")).scalar_one()
        revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        recovery = bool(conn.execute(text("SELECT pg_is_in_recovery()")).scalar_one())
        read_only = conn.execute(text("SELECT current_setting('transaction_read_only')")).scalar_one()
        if db != EXPECTED_DATABASE or revision != EXPECTED_REVISION or recovery or read_only != "off":
            raise RuntimeError(
                f"wrong target db={db!r} revision={revision!r} "
                f"recovery={recovery} read_only={read_only!r}"
            )

        markers = conn.execute(
            text(
                """
                SELECT event_id
                FROM collection_events
                WHERE event_type = :event_type
                  AND metadata->>'run_number' = :run_number
                ORDER BY event_id
                """
            ),
            {"event_type": RUN_MARKER_EVENT_TYPE, "run_number": str(RUN_NUMBER)},
        ).scalars().all()
        if len(markers) != 1:
            raise RuntimeError(f"expected exactly one Step 6 marker; found {len(markers)}")
        boundary = int(markers[0])

        jobs = conn.execute(
            text(
                """
                SELECT soldier_id, resource, lane, priority_class, reason, status,
                       attempt_count, collector_uuid, lease_token, claimed_at,
                       started_at, lease_expires_at
                FROM collection_jobs
                WHERE soldier_id = ANY(:ids)
                ORDER BY soldier_id, resource
                """
            ),
            {"ids": list(SOLDIER_IDS)},
        ).mappings().all()
        if len(jobs) != 27:
            raise RuntimeError(f"expected 27 Step 6 jobs; found {len(jobs)}")
        pairs = {(int(row["soldier_id"]), str(row["resource"])) for row in jobs}
        expected_pairs = {(soldier_id, resource) for soldier_id in SOLDIER_IDS for resource in RESOURCES}
        if pairs != expected_pairs:
            raise RuntimeError("Step 6 soldier/resource queue pairs are not exact")
        for row in jobs:
            if (
                row["lane"] != "background"
                or row["priority_class"] != "bootstrap"
                or row["reason"] != "phase5b_step6_bounded_live"
                or row["status"] != "pending"
                or int(row["attempt_count"]) != 0
                or row["collector_uuid"] is not None
                or row["lease_token"] is not None
                or row["claimed_at"] is not None
                or row["started_at"] is not None
                or row["lease_expires_at"] is not None
            ):
                raise RuntimeError(f"Step 6 queue is not pristine: {dict(row)}")

        foreign_background = int(
            conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM collection_jobs
                    WHERE lane = 'background'
                      AND NOT (
                          soldier_id = ANY(:ids)
                          AND resource = ANY(:resources)
                      )
                    """
                ),
                {"ids": list(SOLDIER_IDS), "resources": list(RESOURCES)},
            ).scalar_one()
        )
        if foreign_background:
            raise RuntimeError(f"foreign background jobs present: {foreign_background}")

        attempts = int(
            conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM (
                        SELECT job_id, attempt_number
                        FROM collection_events
                        WHERE event_id > :boundary
                          AND soldier_id = ANY(:ids)
                          AND resource = ANY(:resources)
                          AND lane = 'background'
                          AND event_type = 'collection_attempt_started'
                        GROUP BY job_id, attempt_number
                    ) AS attempts
                    """
                ),
                {
                    "boundary": boundary,
                    "ids": list(SOLDIER_IDS),
                    "resources": list(RESOURCES),
                },
            ).scalar_one()
        )
        if attempts != 0:
            raise RuntimeError(f"expected zero physical attempts after marker; found {attempts}")

        registry = conn.execute(
            text(
                """
                SELECT collector_uuid, collector_name, hostname, lane, egress_key,
                       enabled, drained, current_job_id, retired_at
                FROM collectors
                WHERE collector_uuid = ANY(:uuids)
                ORDER BY hostname
                """
            ),
            {"uuids": list(FROZEN_UUIDS)},
        ).mappings().all()
        if len(registry) != len(HOSTS):
            raise RuntimeError(
                f"expected {len(HOSTS)} frozen collector registry rows; found {len(registry)}"
            )
        by_uuid = {row["collector_uuid"]: row for row in registry}
        for hostname, frozen in HOSTS.items():
            row = by_uuid.get(frozen.collector_uuid)
            if row is None:
                raise RuntimeError(f"missing frozen collector UUID for {hostname}")
            actual = (
                row["collector_name"],
                row["hostname"],
                row["lane"],
                row["egress_key"],
            )
            expected = (
                frozen.collector_name,
                hostname,
                "background",
                frozen.egress_key,
            )
            if actual != expected:
                raise RuntimeError(
                    f"collector identity drift for {hostname}: actual={actual!r} expected={expected!r}"
                )
            if row["retired_at"] is not None:
                raise RuntimeError(f"collector {hostname} is retired")
            if not bool(row["enabled"]):
                raise RuntimeError(f"collector {hostname} is disabled")
            if bool(row["drained"]):
                raise RuntimeError(f"collector {hostname} is drained")
            if row["current_job_id"] is not None:
                raise RuntimeError(f"collector {hostname} already owns current_job_id={row['current_job_id']}")

    engine.dispose()
    print("===== BF4PS PHASE 5B STEP 6 LAUNCH PREFLIGHT =====")
    print(f"database={EXPECTED_DATABASE} revision={EXPECTED_REVISION} primary_writable=yes")
    print(f"run_marker_event_id={boundary}")
    print("cohort_queue=27 pending/bootstrap/background/attempt0/unowned")
    print("foreign_background_jobs=0")
    print("physical_attempts_after_marker=0")
    print("collectors=hnl-01,kah-01,tcou identity/enabled/undrained/idle: PASS")
    print(f"aggregate_physical_attempt_ceiling={GLOBAL_ATTEMPT_CEILING}")
    print("database writes: 0")
    print("Battlelog requests: 0")
    print("PHASE 5B STEP 6 LAUNCH PREFLIGHT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
