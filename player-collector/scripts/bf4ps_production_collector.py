"""Long-running BF4PS production background collector.

This is orchestration only: queue ordering, budget/fairness, retry state,
request pacing, and persistence remain in the existing production primitives.
"""
from __future__ import annotations

import os
import json
from pathlib import Path
import signal
import socket
import time

from sqlalchemy import create_engine, text

from bf4ps.collector_runtime import heartbeat_collector, register_collector, stop_collector
from bf4ps.detailed_collector import CollectedJob, FailedJob, CollectorIdentity, collect_one_detailed_job
from bf4ps.production_hosts import HOSTS, LEASE_SECONDS, REQUEST_INTERVAL_SECONDS, RESOURCES, SOFTWARE_VERSION, resolve_production_host
from bf4ps.vehicle_collector import CollectedVehicleJob, FailedVehicleJob, collect_one_vehicle_job
from bf4ps.weapon_collector import CollectedWeaponJob, FailedWeaponJob, collect_one_weapon_job
from bf4ps.profile_collector import CollectedProfileJob, FailedProfileJob, collect_one_profile_job
from bf4ps.physical_dispatch_gate import PhysicalDispatchBudgetExhausted

STOP = False
HEARTBEAT_SECONDS = 15.0
IDLE_SLEEP_SECONDS = 0.5
BUDGET_WAIT_SECONDS = 15.0
THROTTLE_COOLDOWN_SECONDS = 900
COOLDOWN_FILE = Path(os.environ.get("BF4PS_COOLDOWN_FILE", "/var/lib/bf4ps-cooldown/until.json"))


def read_cooldown_until() -> float:
    # Fail closed: corrupt/unreadable state must never bypass an active cooldown.
    try:
        return float(json.loads(COOLDOWN_FILE.read_text())["until"])
    except FileNotFoundError:
        return 0.0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise RuntimeError(f"cooldown state unavailable: {COOLDOWN_FILE}") from exc


def persist_cooldown(seconds: int) -> float:
    if seconds < THROTTLE_COOLDOWN_SECONDS:
        seconds = THROTTLE_COOLDOWN_SECONDS
    COOLDOWN_FILE.parent.mkdir(parents=True, exist_ok=True)
    until = max(read_cooldown_until(), time.time() + seconds)
    tmp = COOLDOWN_FILE.with_suffix(".tmp")
    try:
        with tmp.open("w") as f:
            json.dump({"until": until}, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, COOLDOWN_FILE)
        directory_fd = os.open(COOLDOWN_FILE.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        tmp.unlink(missing_ok=True)
    return until


def request_stop(*_args) -> None:
    global STOP
    STOP = True


def collect_one(engine, identity: CollectorIdentity, resource: str, *, allowed_soldier_ids=None, max_total_attempts=None):
    common = dict(
        identity=identity,
        request_interval_seconds=REQUEST_INTERVAL_SECONDS,
        lease_seconds=LEASE_SECONDS,
        enforce_production_budget=True,
        allowed_soldier_ids=allowed_soldier_ids,
        max_total_attempts=max_total_attempts,
    )
    if resource == "detailed":
        return collect_one_detailed_job(engine, timeout_seconds=30.0, **common)
    if resource == "weapons":
        return collect_one_weapon_job(engine, timeout_seconds=30.0, **common)
    if resource == "vehicles":
        return collect_one_vehicle_job(engine, timeout_seconds=30.0, **common)
    if resource == "profile":
        return collect_one_profile_job(engine, timeout_seconds=30.0, **common)
    raise ValueError(f"unsupported production resource: {resource}")


def describe_result(resource: str, result) -> tuple[str, bool]:
    if isinstance(result, (CollectedJob, CollectedWeaponJob, CollectedVehicleJob, CollectedProfileJob)):
        return (
            f"SUCCESS resource={resource} soldier={result.soldier_id} "
            f"job={result.job_id} platform={result.platform} duration_ms={result.duration_ms}",
            False,
        )
    if isinstance(result, (FailedJob, FailedWeaponJob, FailedVehicleJob, FailedProfileJob)):
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
    try:
        host, configured = resolve_production_host()
    except ValueError as exc:
        raise SystemExit(f"REFUSING: {exc}") from exc

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
    # Check host-persistent state before registering or attempting any requests.
    # The mount must exist, including on first startup, or fail closed.
    if not COOLDOWN_FILE.parent.is_dir():
        raise SystemExit(f"REFUSING: persistent cooldown mount missing: {COOLDOWN_FILE.parent}")
    read_cooldown_until()
    engine = create_engine(url, pool_pre_ping=True)

    # Refuse to register, claim, or send anything on an unprepared database.
    # This is a read-only startup preflight; schema upgrades are operator-led.
    with engine.connect() as conn:
        db_name = conn.execute(text("SELECT current_database()")).scalar_one()
        if db_name != "bf4_playerstats":
            raise SystemExit(f"REFUSING: production collector database is {db_name!r}")
        revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        # Revisions 0009-0019 are additive descendants of the physical
        # dispatch gate. A strict equality check to 0008 stopped the entire
        # collector fleet when ranking schema 0018 was installed.
        supported_revisions = frozenset({
            "0008_runtime_budgets", "0009_manual_requests",
            "0010_manual_api_function", "0011_manual_verification",
            "0012_manual_verify_api", "0013_indexed_equipment_rankings",
            "0014_equipment_populations", "0015_rank_generations",
            "0016_rank_scope_versions", "0017_rank_immutable_scores",
            "0018_distributed_rank_queue",
            "0019_soldier_search_trigrams",
            "0020_compact_rank_snapshots", "0021_reconcile_player_exclusions",
            "0022_compact_blocks_only_format", "0023_compact_exclusion_guard",
        })
        if revision not in supported_revisions:
            raise SystemExit(f"REFUSING: unverified production schema revision {revision!r}")
        required_tables = ("outbound_dispatches", "runtime_budgets", "collectors", "collection_jobs")
        missing = [name for name in required_tables if conn.execute(
            text("SELECT to_regclass(:table_name)"),
            {"table_name": "public." + name},
        ).scalar_one() is None]
        if missing:
            raise SystemExit(f"REFUSING: physical dispatch gate tables missing: {missing!r}")

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

            remaining = read_cooldown_until() - time.time()
            if remaining > 0:
                time.sleep(min(HEARTBEAT_SECONDS, remaining))
                continue

            if not control.enabled:
                print("collector disabled; clean stop", flush=True)
                break
            if control.drained:
                time.sleep(IDLE_SLEEP_SECONDS)
                continue

            resource = RESOURCES[resource_index]
            resource_index = (resource_index + 1) % len(RESOURCES)
            try:
                result = collect_one(engine, identity, resource)
            except PhysicalDispatchBudgetExhausted:
                # Fail closed: never retry the HTTP request outside the gate.
                # The claimed lease expires naturally for another cycle.
                print("PHYSICAL DISPATCH BUDGET EXHAUSTED; waiting for capacity", flush=True)
                time.sleep(BUDGET_WAIT_SECONDS)
                continue
            if result is None:
                time.sleep(IDLE_SLEEP_SECONDS)
                continue

            message, throttle = describe_result(resource, result)
            print(message, flush=True)
            if throttle:
                until = persist_cooldown(getattr(result, "retry_after_seconds", 0) or THROTTLE_COOLDOWN_SECONDS)
                print(f"THROTTLE SIGNAL; persistent cooldown until_epoch={until:.0f}; no HTTP during cooldown", flush=True)
                continue
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