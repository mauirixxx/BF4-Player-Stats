#!/usr/bin/env python3
"""Distributed Phase 5A Stage A worker: frozen cohort, weapons only, 30 attempts."""
from __future__ import annotations

import os
import signal
import socket
import time
from urllib.parse import urlsplit

from sqlalchemy import create_engine, text

from bf4ps.collector_runtime import heartbeat_collector, register_collector, stop_collector
from bf4ps.weapon_collector import (
    CollectorIdentity, CollectedWeaponJob, FailedWeaponJob, collect_one_weapon_job,
)
from phase5a_stage_a_common import (
    EXPECTED_DATABASE, FROZEN_UUIDS, GLOBAL_ATTEMPT_CEILING,
    HOSTS, LEASE_SECONDS, REQUEST_INTERVAL_SECONDS, RETRY_AFTER_SECONDS,
    SOFTWARE_VERSION, SOLDIER_IDS, assert_target, current_run_start_event_id,
    terminal_attempts,
)

STOP = False

def request_stop(*_) -> None:
    global STOP
    STOP = True

def safety(conn, *, run_start_event_id: int) -> int:
    assert_target(conn)
    foreign = int(conn.execute(text("""
        SELECT count(*) FROM collection_jobs
        WHERE lane='background'
          AND NOT (resource='weapons' AND soldier_id=ANY(:ids))
    """), {"ids": list(SOLDIER_IDS), "run_start_event_id": run_start_event_id}).scalar_one())
    bad_cohort_job = int(conn.execute(text("""
        SELECT count(*) FROM collection_jobs
        WHERE soldier_id=ANY(:ids)
          AND (resource <> 'weapons' OR lane <> 'background')
    """), {"ids": list(SOLDIER_IDS)}).scalar_one())
    bad_owner = int(conn.execute(text("""
        SELECT count(*) FROM collection_jobs
        WHERE resource='weapons' AND lane='background'
          AND soldier_id=ANY(:ids)
          AND status IN ('claimed','running')
          AND collector_uuid <> ALL(:uuids)
    """), {"ids": list(SOLDIER_IDS), "uuids": list(FROZEN_UUIDS)}).scalar_one())
    n = terminal_attempts(conn, after_event_id=run_start_event_id)
    throttle = int(conn.execute(text("""
        SELECT count(*) FROM collection_events
        WHERE resource='weapons' AND lane='background'
          AND soldier_id=ANY(:ids)
          AND event_id > :run_start_event_id
          AND (http_status IN (403,429) OR error_class='battlelog_throttle')
    """), {"ids": list(SOLDIER_IDS)}).scalar_one())
    if foreign or bad_cohort_job or bad_owner or n > GLOBAL_ATTEMPT_CEILING or throttle:
        raise RuntimeError(
            f"Stage A safety failed foreign={foreign} bad_cohort_job={bad_cohort_job} "
            f"bad_owner={bad_owner} terminal={n} throttle={throttle}"
        )
    return n

def main() -> int:
    host = socket.gethostname().split(".", 1)[0]
    frozen = HOSTS.get(host)
    if frozen is None:
        raise SystemExit(f"REFUSING: host {host!r} is not a frozen Phase 5A collector")

    url = os.environ.get("BF4PS_DATABASE_URL")
    parsed = urlsplit(url or "")
    if not url or parsed.path.lstrip("/") != EXPECTED_DATABASE:
        raise SystemExit("REFUSING: wrong or missing BF4PS_DATABASE_URL")

    identity = CollectorIdentity(
        frozen.collector_uuid, frozen.collector_name, host, frozen.egress_key, "background"
    )
    engine = create_engine(url, pool_pre_ping=True)

    with engine.begin() as conn:
        run_start_event_id = current_run_start_event_id(conn)
        n = safety(conn, run_start_event_id=run_start_event_id)
        control = register_collector(conn, identity=identity, software_version=SOFTWARE_VERSION)

    print("===== BF4PS PHASE 5A STAGE A DISTRIBUTED WEAPON WORKER =====", flush=True)
    print(
        f"host={host} collector={frozen.collector_name} egress={frozen.egress_key}\n"
        f"frozen soldiers={len(SOLDIER_IDS)} global attempt ceiling={GLOBAL_ATTEMPT_CEILING}\n"
        f"request spacing={REQUEST_INTERVAL_SECONDS:.1f}s retry deferral={RETRY_AFTER_SECONDS}s\n"
        f"initial terminal attempts={n} drained={control.drained}",
        flush=True,
    )

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    local_attempts = 0
    try:
        while not STOP:
            with engine.begin() as conn:
                n = safety(conn, run_start_event_id=run_start_event_id)
                control = heartbeat_collector(
                    conn, collector_uuid=frozen.collector_uuid, software_version=SOFTWARE_VERSION
                )
            if not control.enabled:
                print("collector disabled; clean stop", flush=True)
                break
            if n >= GLOBAL_ATTEMPT_CEILING:
                print("global 30-attempt ceiling reached", flush=True)
                break
            if control.drained:
                time.sleep(0.5)
                continue

            outcome = collect_one_weapon_job(
                engine,
                identity=identity,
                request_interval_seconds=REQUEST_INTERVAL_SECONDS,
                lease_seconds=LEASE_SECONDS,
                timeout_seconds=30,
                retry_after_seconds=RETRY_AFTER_SECONDS,
                allowed_soldier_ids=SOLDIER_IDS,
                max_total_attempts=GLOBAL_ATTEMPT_CEILING,
                attempts_after_event_id=run_start_event_id,
            )
            if outcome is None:
                time.sleep(0.25)
                continue

            local_attempts += 1
            if isinstance(outcome, CollectedWeaponJob):
                print(
                    f"[{local_attempts:02d}] SUCCESS soldier={outcome.soldier_id} "
                    f"job={outcome.job_id} platform={outcome.platform} rows={outcome.weapon_rows} "
                    f"bytes={outcome.response_bytes} duration_ms={outcome.duration_ms}",
                    flush=True,
                )
            elif isinstance(outcome, FailedWeaponJob):
                print(
                    f"[{local_attempts:02d}] FAILURE soldier={outcome.soldier_id} "
                    f"job={outcome.job_id} platform={outcome.platform} http={outcome.http_status} "
                    f"class={outcome.error_class} duration_ms={outcome.duration_ms}",
                    flush=True,
                )
                if outcome.http_status in {403, 429} or outcome.error_class == "battlelog_throttle":
                    print("THROTTLE SIGNAL; stopping", flush=True)
                    break
    finally:
        with engine.begin() as conn:
            stop_collector(conn, collector_uuid=frozen.collector_uuid)

    print(f"PHASE 5A STAGE A WORKER STOPPED CLEANLY host={host} local_attempts={local_attempts}", flush=True)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
