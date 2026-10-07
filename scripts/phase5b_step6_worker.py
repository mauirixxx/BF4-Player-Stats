#!/usr/bin/env python3
"""Phase 5B Step 6 bounded live distributed worker."""
from __future__ import annotations

import os
import signal
import socket
import time
from urllib.parse import urlsplit

from sqlalchemy import create_engine, text

from bf4ps.collector_runtime import heartbeat_collector, register_collector, stop_collector
from bf4ps.detailed_collector import (
    CollectorIdentity,
    CollectedJob,
    FailedJob,
    collect_one_detailed_job,
)
from bf4ps.vehicle_collector import (
    CollectedVehicleJob,
    FailedVehicleJob,
    collect_one_vehicle_job,
)
from bf4ps.weapon_collector import (
    CollectedWeaponJob,
    FailedWeaponJob,
    collect_one_weapon_job,
)
from bf4ps.phase5b_step6_cohort import (
    EXPECTED_DATABASE,
    EXPECTED_REVISION,
    FROZEN_UUIDS,
    GLOBAL_ATTEMPT_CEILING,
    HOSTS,
    LEASE_SECONDS,
    REQUEST_INTERVAL_SECONDS,
    RESOURCES,
    RUN_MARKER_EVENT_TYPE,
    RUN_NUMBER,
    SOFTWARE_VERSION,
    SOLDIER_IDS,
)

STOP = False


def request_stop(*_) -> None:
    global STOP
    STOP = True


def _assert_target(conn) -> None:
    db = conn.execute(text("SELECT current_database()")).scalar_one()
    revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    recovery = bool(conn.execute(text("SELECT pg_is_in_recovery()")).scalar_one())
    read_only = conn.execute(text("SELECT current_setting('transaction_read_only')")).scalar_one()
    if db != EXPECTED_DATABASE or revision != EXPECTED_REVISION or recovery or read_only != "off":
        raise RuntimeError(
            f"wrong target db={db!r} revision={revision!r} "
            f"recovery={recovery} read_only={read_only!r}"
        )


def _run_boundary(conn) -> int:
    rows = conn.execute(
        text(
            """
            SELECT event_id
            FROM collection_events
            WHERE event_type = :event_type
              AND metadata->>'run_number' = :run_number
            ORDER BY event_id DESC
            """
        ),
        {"event_type": RUN_MARKER_EVENT_TYPE, "run_number": str(RUN_NUMBER)},
    ).scalars().all()
    if len(rows) != 1:
        raise RuntimeError(f"expected exactly one Step 6 run marker; found {len(rows)}")
    return int(rows[0])


def _physical_attempts(conn, *, boundary: int) -> int:
    return int(
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


def safety(conn, *, boundary: int) -> int:
    _assert_target(conn)
    foreign = int(
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
    bad_cohort_job = int(
        conn.execute(
            text(
                """
                SELECT COUNT(*)
                FROM collection_jobs
                WHERE soldier_id = ANY(:ids)
                  AND (
                      resource <> ALL(:resources)
                      OR lane <> 'background'
                  )
                """
            ),
            {"ids": list(SOLDIER_IDS), "resources": list(RESOURCES)},
        ).scalar_one()
    )
    bad_owner = int(
        conn.execute(
            text(
                """
                SELECT COUNT(*)
                FROM collection_jobs
                WHERE soldier_id = ANY(:ids)
                  AND resource = ANY(:resources)
                  AND lane = 'background'
                  AND status IN ('claimed', 'running')
                  AND collector_uuid <> ALL(:uuids)
                """
            ),
            {"ids": list(SOLDIER_IDS), "resources": list(RESOURCES), "uuids": list(FROZEN_UUIDS)},
        ).scalar_one()
    )
    attempts = _physical_attempts(conn, boundary=boundary)
    throttle = int(
        conn.execute(
            text(
                """
                SELECT COUNT(*)
                FROM collection_events
                WHERE event_id > :boundary
                  AND soldier_id = ANY(:ids)
                  AND resource = ANY(:resources)
                  AND lane = 'background'
                  AND (
                      http_status IN (403, 429)
                      OR error_class = 'battlelog_throttle'
                  )
                """
            ),
            {"boundary": boundary, "ids": list(SOLDIER_IDS), "resources": list(RESOURCES)},
        ).scalar_one()
    )
    persistence_failures = int(
        conn.execute(
            text(
                """
                SELECT COUNT(*)
                FROM collection_events
                WHERE event_id > :boundary
                  AND soldier_id = ANY(:ids)
                  AND resource = ANY(:resources)
                  AND event_type = 'collection_persistence_failure'
                """
            ),
            {"boundary": boundary, "ids": list(SOLDIER_IDS), "resources": list(RESOURCES)},
        ).scalar_one()
    )
    if (
        foreign
        or bad_cohort_job
        or bad_owner
        or attempts > GLOBAL_ATTEMPT_CEILING
        or throttle
        or persistence_failures
    ):
        raise RuntimeError(
            "Step 6 safety failed "
            f"foreign={foreign} bad_cohort_job={bad_cohort_job} bad_owner={bad_owner} "
            f"physical_attempts={attempts} throttle={throttle} "
            f"persistence_failures={persistence_failures}"
        )
    return attempts


def _collect_one(engine, *, identity: CollectorIdentity, resource: str, boundary: int):
    common = dict(
        identity=identity,
        request_interval_seconds=REQUEST_INTERVAL_SECONDS,
        lease_seconds=LEASE_SECONDS,
        allowed_soldier_ids=SOLDIER_IDS,
        max_total_attempts=GLOBAL_ATTEMPT_CEILING,
        attempts_after_event_id=boundary,
        attempt_ceiling_resources=RESOURCES,
        enforce_production_budget=True,
    )
    if resource == "detailed":
        return collect_one_detailed_job(engine, timeout_seconds=30.0, **common)
    if resource == "weapons":
        return collect_one_weapon_job(engine, timeout_seconds=30.0, **common)
    if resource == "vehicles":
        return collect_one_vehicle_job(engine, timeout_seconds=30.0, **common)
    raise RuntimeError(f"unsupported Step 6 resource {resource!r}")


def _print_outcome(local_attempts: int, resource: str, outcome) -> bool:
    if isinstance(outcome, (CollectedJob, CollectedWeaponJob, CollectedVehicleJob)):
        extra = ""
        if isinstance(outcome, CollectedWeaponJob):
            extra = f" rows={outcome.weapon_rows} bytes={outcome.response_bytes}"
        elif isinstance(outcome, CollectedVehicleJob):
            extra = f" rows={outcome.vehicle_rows} bytes={outcome.response_bytes}"
        print(
            f"[{local_attempts:02d}] SUCCESS resource={resource} soldier={outcome.soldier_id} "
            f"job={outcome.job_id} platform={outcome.platform}{extra} "
            f"duration_ms={outcome.duration_ms}",
            flush=True,
        )
        return False

    if isinstance(outcome, (FailedJob, FailedWeaponJob, FailedVehicleJob)):
        print(
            f"[{local_attempts:02d}] FAILURE resource={resource} soldier={outcome.soldier_id} "
            f"job={outcome.job_id} platform={outcome.platform} http={outcome.http_status} "
            f"class={outcome.error_class} retry_after={outcome.retry_after_seconds}s "
            f"duration_ms={outcome.duration_ms}",
            flush=True,
        )
        return outcome.http_status in {403, 429} or outcome.error_class == "battlelog_throttle"

    raise RuntimeError(f"unexpected collector outcome type: {type(outcome)!r}")


def main() -> int:
    host = socket.gethostname().split(".", 1)[0]
    frozen = HOSTS.get(host)
    if frozen is None:
        raise SystemExit(f"REFUSING: host {host!r} is not a frozen Step 6 collector")

    url = os.environ.get("BF4PS_DATABASE_URL")
    parsed = urlsplit(url or "")
    if not url or parsed.path.lstrip("/") != EXPECTED_DATABASE:
        raise SystemExit("REFUSING: wrong or missing BF4PS_DATABASE_URL")

    identity = CollectorIdentity(
        frozen.collector_uuid,
        frozen.collector_name,
        host,
        frozen.egress_key,
        "background",
    )
    engine = create_engine(url, pool_pre_ping=True)

    with engine.begin() as conn:
        boundary = _run_boundary(conn)
        attempts = safety(conn, boundary=boundary)
        control = register_collector(conn, identity=identity, software_version=SOFTWARE_VERSION)

    print("===== BF4PS PHASE 5B STEP 6 BOUNDED LIVE WORKER =====", flush=True)
    print(
        f"host={host} collector={frozen.collector_name} egress={frozen.egress_key}\n"
        f"run_marker_event_id={boundary} soldiers={len(SOLDIER_IDS)} resources={','.join(RESOURCES)}\n"
        f"global physical-attempt ceiling={GLOBAL_ATTEMPT_CEILING} "
        f"request spacing={REQUEST_INTERVAL_SECONDS:.1f}s production_budget=enabled\n"
        f"initial physical attempts={attempts} drained={control.drained}",
        flush=True,
    )

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    local_attempts = 0
    resource_index = 0
    empty_rounds = 0
    try:
        while not STOP:
            with engine.begin() as conn:
                attempts = safety(conn, boundary=boundary)
                control = heartbeat_collector(
                    conn,
                    collector_uuid=frozen.collector_uuid,
                    software_version=SOFTWARE_VERSION,
                )
            if not control.enabled:
                print("collector disabled; clean stop", flush=True)
                break
            if attempts >= GLOBAL_ATTEMPT_CEILING:
                print("global 27-physical-attempt ceiling reached", flush=True)
                break
            if control.drained:
                time.sleep(0.5)
                continue

            resource = RESOURCES[resource_index]
            resource_index = (resource_index + 1) % len(RESOURCES)
            outcome = _collect_one(
                engine,
                identity=identity,
                resource=resource,
                boundary=boundary,
            )
            if outcome is None:
                empty_rounds += 1
                if empty_rounds >= len(RESOURCES):
                    with engine.connect() as conn:
                        remaining = int(
                            conn.execute(
                                text(
                                    """
                                    SELECT COUNT(*)
                                    FROM collection_jobs
                                    WHERE soldier_id = ANY(:ids)
                                      AND resource = ANY(:resources)
                                      AND lane = 'background'
                                      AND eligible_at <= now()
                                    """
                                ),
                                {"ids": list(SOLDIER_IDS), "resources": list(RESOURCES)},
                            ).scalar_one()
                        )
                    if remaining == 0:
                        print("no eligible Step 6 cohort work remains", flush=True)
                        break
                    empty_rounds = 0
                time.sleep(0.25)
                continue

            empty_rounds = 0
            local_attempts += 1
            if _print_outcome(local_attempts, resource, outcome):
                print("THROTTLE SIGNAL; stopping", flush=True)
                break
    finally:
        with engine.begin() as conn:
            stop_collector(conn, collector_uuid=frozen.collector_uuid)
        engine.dispose()

    print(
        f"PHASE 5B STEP 6 WORKER STOPPED CLEANLY host={host} local_attempts={local_attempts}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
