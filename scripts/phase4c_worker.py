#!/usr/bin/env python3
"""Phase 4C 450-player multiplatform sustained worker using production collection."""
from __future__ import annotations

import os
import signal
import socket
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parent))

from phase4c_cohort import SOLDIER_IDS
from phase4c_common import (
    EXPECTED_DATABASE,
    EXPECTED_DB_HOST,
    FROZEN_UUIDS,
    GLOBAL_ATTEMPT_CEILING,
    HOSTS,
    LEASE_SECONDS,
    REQUEST_INTERVAL_SECONDS,
    TARGET_DEPTH,
    assert_target,
    terminal_attempts,
)
from bf4ps.bounded_feeder import replenish_detailed_bootstrap
from bf4ps.collector_runtime import heartbeat_collector, register_collector, stop_collector
from bf4ps.detailed_collector import (
    CollectorIdentity,
    CollectedJob,
    FailedJob,
    collect_one_detailed_job,
)

STOP = False


def request_stop(*_) -> None:
    global STOP
    STOP = True


def safety(conn) -> int:
    assert_target(conn)
    ids = list(SOLDIER_IDS)
    foreign = int(
        conn.execute(
            text("SELECT count(*) FROM collection_jobs WHERE resource='detailed' AND lane='background' AND soldier_id <> ALL(:ids)"),
            {"ids": ids},
        ).scalar_one()
    )
    bad_owner = int(
        conn.execute(
            text("SELECT count(*) FROM collection_jobs WHERE resource='detailed' AND lane='background' AND soldier_id=ANY(:ids) AND status IN ('claimed','running') AND collector_uuid <> ALL(:uuids)"),
            {"ids": ids, "uuids": list(FROZEN_UUIDS)},
        ).scalar_one()
    )
    n = terminal_attempts(conn)
    throttle = int(
        conn.execute(
            text("SELECT count(*) FROM collection_events WHERE resource='detailed' AND lane='background' AND soldier_id=ANY(:ids) AND (http_status IN (403,429) OR error_class='battlelog_throttle')"),
            {"ids": ids},
        ).scalar_one()
    )
    if foreign or bad_owner or n > GLOBAL_ATTEMPT_CEILING or throttle:
        raise RuntimeError(
            f"Phase 4C safety boundary failed foreign={foreign} bad_owner={bad_owner} terminal={n} throttle={throttle}"
        )
    return n


def main() -> None:
    host = socket.gethostname().split(".", 1)[0]
    frozen = HOSTS.get(host)
    if not frozen:
        raise SystemExit(f"REFUSING: host {host!r} is not a frozen Phase 4C collector")

    url = os.environ.get("BF4PS_DATABASE_URL")
    parsed = urlsplit(url or "")
    if not url or parsed.hostname != EXPECTED_DB_HOST or parsed.path.lstrip("/") != EXPECTED_DATABASE:
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
        n = safety(conn)
        control = register_collector(
            conn,
            identity=identity,
            software_version="phase4c-450-multiplatform-sustained",
        )

    print("===== BF4PS PHASE 4C 450-PLAYER MULTIPLATFORM SUSTAINED WORKER =====", flush=True)
    print(
        f"host: {host}\n"
        f"collector: {frozen.collector_name} {frozen.collector_uuid}\n"
        f"egress: {frozen.egress_key}\n"
        f"frozen cohort: {len(SOLDIER_IDS)} soldiers (150 PC / 150 PS4 / 150 Xbox One)\n"
        f"target actionable depth: {TARGET_DEPTH}\n"
        f"global terminal-attempt ceiling: {GLOBAL_ATTEMPT_CEILING}\n"
        f"request spacing: {REQUEST_INTERVAL_SECONDS:.1f}s\n"
        f"initial terminal attempts: {n}\n"
        f"initial drained: {control.drained}",
        flush=True,
    )

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    local_attempts = feeder_passes = feeder_created = max_observed_depth = 0
    was_drained = None

    try:
        while not STOP:
            with engine.begin() as conn:
                n = safety(conn)
                control = heartbeat_collector(
                    conn,
                    collector_uuid=frozen.collector_uuid,
                    software_version="phase4c-450-multiplatform-sustained",
                )
                feed = None
                if control.may_claim and n < GLOBAL_ATTEMPT_CEILING:
                    feed = replenish_detailed_bootstrap(
                        conn,
                        target_depth=TARGET_DEPTH,
                        max_soldier_id=max(SOLDIER_IDS),
                        allowed_soldier_ids=SOLDIER_IDS,
                        max_total_attempts=GLOBAL_ATTEMPT_CEILING,
                    )
                    feeder_passes += 1
                    feeder_created += feed.created
                    max_observed_depth = max(
                        max_observed_depth,
                        feed.actionable_before,
                        feed.actionable_after,
                    )

            if control.drained != was_drained:
                print(f"CONTROL BOUNDARY drained={control.drained} terminal={n}", flush=True)
                was_drained = control.drained
            if feed is not None and feed.created:
                print(
                    f"FEED pass={feeder_passes} before={feed.actionable_before} "
                    f"deficit={feed.deficit} created={feed.created} "
                    f"after={feed.actionable_after} terminal={n}",
                    flush=True,
                )
            if not control.enabled:
                print("collector disabled; clean stop", flush=True)
                break
            if n >= GLOBAL_ATTEMPT_CEILING:
                print("global attempt ceiling reached", flush=True)
                break
            if control.drained:
                time.sleep(1)
                continue

            outcome = collect_one_detailed_job(
                engine,
                identity=identity,
                request_interval_seconds=REQUEST_INTERVAL_SECONDS,
                lease_seconds=LEASE_SECONDS,
                timeout_seconds=15,
                retry_after_seconds=300,
                allowed_soldier_ids=SOLDIER_IDS,
                max_total_attempts=GLOBAL_ATTEMPT_CEILING,
            )
            if outcome is None:
                time.sleep(0.5)
                continue

            local_attempts += 1
            if isinstance(outcome, CollectedJob):
                print(
                    f"[{local_attempts:03d}] SUCCESS soldier={outcome.soldier_id} "
                    f"job={outcome.job_id} {outcome.platform}",
                    flush=True,
                )
            elif isinstance(outcome, FailedJob):
                print(
                    f"[{local_attempts:03d}] FAILURE soldier={outcome.soldier_id} "
                    f"job={outcome.job_id} http={outcome.http_status} class={outcome.error_class}",
                    flush=True,
                )
                if outcome.http_status in {403, 429} or outcome.error_class == "battlelog_throttle":
                    print("THROTTLE SIGNAL; stopping", flush=True)
                    break
    finally:
        with engine.begin() as conn:
            stop_collector(conn, collector_uuid=frozen.collector_uuid)

    print(
        f"PHASE 4C WORKER STOPPED CLEANLY host={host} local_attempts={local_attempts} "
        f"feeder_passes={feeder_passes} feeder_created={feeder_created} "
        f"max_observed_depth={max_observed_depth}",
        flush=True,
    )


if __name__ == "__main__":
    main()
