#!/usr/bin/env python3
"""Long-running BF4PS production background collector.

This is orchestration only: queue ordering, budget/fairness, retry state,
request pacing, and persistence remain in the existing production primitives.
"""
from __future__ import annotations

import os
import signal
import socket
import time

from sqlalchemy import create_engine

from bf4ps.collector_runtime import heartbeat_collector, register_collector, stop_collector
from bf4ps.detailed_collector import CollectedJob, FailedJob, CollectorIdentity, collect_one_detailed_job
from bf4ps.production_hosts import HOSTS, LEASE_SECONDS, REQUEST_INTERVAL_SECONDS, RESOURCES, SOFTWARE_VERSION
from bf4ps.vehicle_collector import CollectedVehicleJob, FailedVehicleJob, collect_one_vehicle_job
from bf4ps.weapon_collector import CollectedWeaponJob, FailedWeaponJob, collect_one_weapon_job

STOP = False
HEARTBEAT_SECONDS = 15.0
IDLE_SLEEP_SECONDS = 0.5


def request_stop(*_args) -> None:
    global STOP
    STOP = True


def collect_one(engine, identity: CollectorIdentity, resource: str):
    common = dict(
        identity=identity,
        request_interval_seconds=REQUEST_INTERVAL_SECONDS,
        lease_seconds=LEASE_SECONDS,
        enforce_production_budget=True,
    )
    if resource == "detailed":
        return collect_one_detailed_job(engine, timeout_seconds=30.0, **common)
    if resource == "weapons":
        return collect_one_weapon_job(engine, timeout_seconds=30.0, **common)
    if resource == "vehicles":
        return collect_one_vehicle_job(engine, timeout_seconds=30.0, **common)
    raise ValueError(f"unsupported production resource: {resource}")


def describe_result(resource: str, result) -> tuple[str, bool]:
    if isinstance(result, (CollectedJob, CollectedWeaponJob, CollectedVehicleJob)):
        return (
            f"SUCCESS resource={resource} soldier={result.soldier_id} "
            f"job={result.job_id} platform={result.platform} duration_ms={result.duration_ms}",
            False,
        )
    if isinstance(result, (FailedJob, FailedWeaponJob, FailedVehicleJob)):
        throttle = result.http_status in {403, 429} or result.error_class == "battlelog_throttle"
        return (
            f"FAILURE resource={resource} soldier={result.soldier_id} "
            f"job={result.job_id} platform={result.platform} http={result.http_status} "
            f"class={result.error_class} retry_after={result.retry_after_seconds}s "
            f"duration_ms={result.duration_ms}",
            throttle,
        )
    raise TypeError(f"unexpected collector result: {type(result)!r}")


def main() -> int:
    host = socket.gethostname().split(".", 1)[0]
    configured = HOSTS.get(host)
    if configured is None:
        raise SystemExit(f"REFUSING: host {host!r} has no production collector identity")

    url = os.environ.get("BF4PS_DATABASE_URL")
    if not url:
        raise SystemExit("REFUSING: BF4PS_DATABASE_URL is required")

    identity = CollectorIdentity(
        configured.collector_uuid,
        configured.collector_name,
        host,
        configured.egress_key,
        "background",
    )
    engine = create_engine(url, pool_pre_ping=True)

    with engine.begin() as conn:
        control = register_collector(conn, identity=identity, software_version=SOFTWARE_VERSION)

    print(
        "BF4PS PRODUCTION COLLECTOR START "
        f"host={host} collector={configured.collector_name} egress={configured.egress_key} "
        f"request_spacing={REQUEST_INTERVAL_SECONDS:.1f}s production_budget=enabled "
        f"enabled={control.enabled} drained={control.drained}",
        flush=True,
    )

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    resource_index = 0
    next_heartbeat = 0.0
    try:
        while not STOP:
            now = time.monotonic()
            if now >= next_heartbeat:
                with engine.begin() as conn:
                    control = heartbeat_collector(
                        conn,
                        collector_uuid=configured.collector_uuid,
                        software_version=SOFTWARE_VERSION,
                    )
                next_heartbeat = now + HEARTBEAT_SECONDS

            if not control.enabled:
                print("collector disabled; clean stop", flush=True)
                break
            if control.drained:
                time.sleep(IDLE_SLEEP_SECONDS)
                continue

            resource = RESOURCES[resource_index]
            resource_index = (resource_index + 1) % len(RESOURCES)
            result = collect_one(engine, identity, resource)
            if result is None:
                time.sleep(IDLE_SLEEP_SECONDS)
                continue

            message, throttle = describe_result(resource, result)
            print(message, flush=True)
            if throttle:
                print("THROTTLE SIGNAL; stopping production collector", flush=True)
                break
    finally:
        try:
            with engine.begin() as conn:
                stop_collector(conn, collector_uuid=configured.collector_uuid)
        finally:
            engine.dispose()

    print(f"BF4PS PRODUCTION COLLECTOR STOPPED CLEANLY host={host}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
