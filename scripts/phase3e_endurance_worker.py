#!/usr/bin/env python3
"""Run a bounded Phase 3E endurance collector on a frozen physical host."""
from __future__ import annotations

import os
import socket
import time
from dataclasses import dataclass
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import create_engine, text

from bf4ps.bounded_feeder import replenish_detailed_bootstrap
from bf4ps.collector_runtime import heartbeat_collector, register_collector, stop_collector
from bf4ps.detailed_collector import CollectedJob, CollectorIdentity, FailedJob, collect_one_detailed_job
from phase3e_frozen_cohort import COHORT_SOLDIER_IDS, GLOBAL_ATTEMPT_CEILING

EXPECTED_DATABASE = "bf4_playerstats_test"
EXPECTED_DB_HOST = "mak-db-02.bf4statusbot.com"
EXPECTED_REVISION = "0003_request_gates"
REQUEST_INTERVAL_SECONDS = 5.0
TARGET_DEPTH = 6
LEASE_SECONDS = 120
IDLE_SLEEP_SECONDS = 1.0
MAX_SOLDIER_ID = max(COHORT_SOLDIER_IDS)


@dataclass(frozen=True)
class FrozenHost:
    collector_uuid: UUID
    collector_name: str
    egress_key: str


# Stable Phase 3E identities deliberately differ from Phase 3D identities.
HOSTS = {
    "hnl-01": FrozenHost(UUID("b2b3ef60-62e8-4d4a-91b0-41a2e2a3e001"), "phase3e-hnl-01", "phase3e-hnl-01"),
    "kah-01": FrozenHost(UUID("b2b3ef60-62e8-4d4a-91b0-41a2e2a3e002"), "phase3e-kah-01", "phase3e-kah-01"),
    "tcou": FrozenHost(UUID("b2b3ef60-62e8-4d4a-91b0-41a2e2a3e003"), "phase3e-tcou", "phase3e-tcou"),
}
FROZEN_UUIDS = frozenset(host.collector_uuid for host in HOSTS.values())


def terminal_attempts(conn) -> int:
    return int(conn.execute(text("""
        SELECT COUNT(*)
        FROM collection_events
        WHERE resource = 'detailed'
          AND lane = 'background'
          AND soldier_id = ANY(:ids)
          AND event_type IN ('collection_success', 'collection_failure')
    """), {"ids": list(COHORT_SOLDIER_IDS)}).scalar_one())


def safety_check(conn) -> tuple[int, int]:
    target = conn.execute(text("""
        SELECT current_database() AS database_name,
               pg_is_in_recovery() AS recovery,
               current_setting('transaction_read_only') AS read_only
    """)).mappings().one()
    revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    if target["database_name"] != EXPECTED_DATABASE or target["recovery"] or target["read_only"] != "off":
        raise RuntimeError("database safety boundary failed")
    if revision != EXPECTED_REVISION:
        raise RuntimeError(f"unexpected Alembic revision {revision!r}")

    foreign = int(conn.execute(text("""
        SELECT COUNT(*) FROM collection_jobs
        WHERE resource = 'detailed' AND lane = 'background'
          AND soldier_id <> ALL(:ids)
    """), {"ids": list(COHORT_SOLDIER_IDS)}).scalar_one())
    if foreign:
        raise RuntimeError("detailed/background queue contains work outside frozen Phase 3E cohort")

    bad_owner = int(conn.execute(text("""
        SELECT COUNT(*) FROM collection_jobs
        WHERE resource = 'detailed' AND lane = 'background'
          AND soldier_id = ANY(:ids)
          AND status IN ('claimed', 'running')
          AND collector_uuid <> ALL(:uuids)
    """), {"ids": list(COHORT_SOLDIER_IDS), "uuids": list(FROZEN_UUIDS)}).scalar_one())
    if bad_owner:
        raise RuntimeError("Phase 3E work is owned by a non-frozen collector")

    attempts = terminal_attempts(conn)
    if attempts > GLOBAL_ATTEMPT_CEILING:
        raise RuntimeError("global Phase 3E attempt ceiling exceeded")

    actionable = int(conn.execute(text("""
        SELECT COUNT(*) FROM collection_jobs
        WHERE resource = 'detailed' AND lane = 'background'
          AND soldier_id = ANY(:ids)
          AND (status IN ('claimed', 'running') OR (status = 'pending' AND eligible_at <= now()))
    """), {"ids": list(COHORT_SOLDIER_IDS)}).scalar_one())
    if actionable > TARGET_DEPTH:
        raise RuntimeError("bounded queue depth exceeded Phase 3E target")
    return attempts, actionable


def main() -> None:
    hostname = socket.gethostname().split(".", 1)[0]
    frozen = HOSTS.get(hostname)
    if frozen is None:
        raise SystemExit(f"REFUSING: host {hostname!r} is not frozen for Phase 3E")

    database_url = os.environ.get("BF4PS_DATABASE_URL")
    if not database_url:
        raise SystemExit("REFUSING: BF4PS_DATABASE_URL is not set")
    parsed = urlsplit(database_url)
    if parsed.hostname != EXPECTED_DB_HOST or parsed.path.lstrip("/") != EXPECTED_DATABASE:
        raise SystemExit("REFUSING: database URL is not the frozen Phase 3E test target")

    identity = CollectorIdentity(
        collector_uuid=frozen.collector_uuid,
        collector_name=frozen.collector_name,
        hostname=hostname,
        egress_key=frozen.egress_key,
        lane="background",
    )
    engine = create_engine(database_url, pool_pre_ping=True)

    with engine.begin() as conn:
        attempts, actionable = safety_check(conn)
        control = register_collector(conn, identity=identity, software_version="phase3e-endurance")
    if not control.may_claim:
        raise SystemExit("REFUSING: collector is disabled or drained")

    print("===== BF4PS PHASE 3E ENDURANCE WORKER =====")
    print(f"host:             {hostname}")
    print(f"collector:        {frozen.collector_name}")
    print(f"collector UUID:   {frozen.collector_uuid}")
    print(f"egress gate:      {frozen.egress_key}")
    print(f"request interval: {REQUEST_INTERVAL_SECONDS:.1f}s")
    print(f"queue target:     {TARGET_DEPTH}")
    print(f"global ceiling:   {GLOBAL_ATTEMPT_CEILING}")
    print(f"terminal before:  {attempts}")
    print(f"actionable before:{actionable}")

    local_attempts = local_success = local_failure = 0
    try:
        while True:
            with engine.begin() as conn:
                attempts, _ = safety_check(conn)
                control = heartbeat_collector(conn, collector_uuid=frozen.collector_uuid)
                if attempts < GLOBAL_ATTEMPT_CEILING:
                    replenish_detailed_bootstrap(
                        conn,
                        target_depth=TARGET_DEPTH,
                        max_soldier_id=MAX_SOLDIER_ID,
                        allowed_soldier_ids=COHORT_SOLDIER_IDS,
                        max_total_attempts=GLOBAL_ATTEMPT_CEILING,
                    )

            if not control.may_claim:
                print("operator control stopped new claims; exiting cleanly")
                break
            if attempts >= GLOBAL_ATTEMPT_CEILING:
                print("global attempt ceiling reached")
                break

            outcome = collect_one_detailed_job(
                engine,
                identity=identity,
                request_interval_seconds=REQUEST_INTERVAL_SECONDS,
                lease_seconds=LEASE_SECONDS,
                timeout_seconds=15.0,
                retry_after_seconds=300,
                allowed_soldier_ids=COHORT_SOLDIER_IDS,
                max_total_attempts=GLOBAL_ATTEMPT_CEILING,
            )
            if outcome is None:
                with engine.connect() as conn:
                    attempts, actionable = safety_check(conn)
                if attempts >= GLOBAL_ATTEMPT_CEILING:
                    print("global attempt ceiling reached")
                    break
                if actionable == 0:
                    time.sleep(IDLE_SLEEP_SECONDS)
                continue

            local_attempts += 1
            if isinstance(outcome, CollectedJob):
                local_success += 1
                print(f"[{local_attempts:03d}] SUCCESS soldier={outcome.soldier_id} job={outcome.job_id} {outcome.platform}", flush=True)
            elif isinstance(outcome, FailedJob):
                local_failure += 1
                print(
                    f"[{local_attempts:03d}] FAILURE soldier={outcome.soldier_id} job={outcome.job_id} "
                    f"{outcome.platform} http={outcome.http_status} class={outcome.error_class}",
                    flush=True,
                )
                if outcome.http_status in {403, 429} or outcome.error_class == "battlelog_throttle":
                    print("THROTTLE SIGNAL: stopping this worker and preserving evidence", flush=True)
                    break
            else:
                raise RuntimeError(f"unexpected collector result {type(outcome)!r}")
    finally:
        with engine.begin() as conn:
            stop_collector(conn, collector_uuid=frozen.collector_uuid)

    with engine.connect() as conn:
        attempts, actionable = safety_check(conn)
        collector = conn.execute(text("""
            SELECT heartbeat_state, enabled, drained, current_job_id
            FROM collectors WHERE collector_uuid = :uuid
        """), {"uuid": frozen.collector_uuid}).mappings().one()
        gate = conn.execute(text("""
            SELECT egress_key FROM request_gates WHERE egress_key = :key
        """), {"key": frozen.egress_key}).mappings().one_or_none()

    if collector["heartbeat_state"] != "unknown" or collector["current_job_id"] is not None:
        raise RuntimeError("collector did not stop cleanly")
    if gate is None and local_attempts:
        raise RuntimeError("request gate was not materialized")

    print("\n===== LOCAL STOP SUMMARY =====")
    print(f"local attempts:    {local_attempts}")
    print(f"success / failure: {local_success} / {local_failure}")
    print(f"global terminal:   {attempts}/{GLOBAL_ATTEMPT_CEILING}")
    print(f"actionable now:    {actionable}/{TARGET_DEPTH}")
    print("collector stop:    PASS")
    print("PHASE 3E ENDURANCE WORKER: STOPPED CLEANLY")


if __name__ == "__main__":
    main()
