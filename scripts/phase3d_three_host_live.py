#!/usr/bin/env python3
"""Run one bounded Phase 3D worker on a frozen physical host."""
from __future__ import annotations

import os
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import create_engine, text

from bf4ps.collector_runtime import heartbeat_collector, register_collector, stop_collector
from bf4ps.detailed_collector import CollectedJob, CollectorIdentity, FailedJob, collect_one_detailed_job

EXPECTED_DATABASE = "bf4_playerstats_test"
EXPECTED_DB_HOST = "mak-db-02.bf4statusbot.com"
EXPECTED_REVISION = "0003_request_gates"
COHORT_IDS = (
    24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35,
    112, 113, 114, 115, 116, 117, 118, 119, 120, 121, 122, 123,
    100, 101, 102, 103, 104, 162, 163, 164, 165, 166, 167, 168,
)
LOCAL_ATTEMPT_CEILING = 12
REQUEST_INTERVAL_SECONDS = 5.0

@dataclass(frozen=True)
class FrozenHost:
    collector_uuid: UUID
    collector_name: str
    egress_key: str

HOSTS = {
    "hnl-01": FrozenHost(UUID("b2b3ef60-62e8-4d4a-91b0-41a2e2a3d001"), "phase3d-hnl-01", "phase3d-hnl-01"),
    "kah-01": FrozenHost(UUID("b2b3ef60-62e8-4d4a-91b0-41a2e2a3d002"), "phase3d-kah-01", "phase3d-kah-01"),
    "tcou": FrozenHost(UUID("b2b3ef60-62e8-4d4a-91b0-41a2e2a3d003"), "phase3d-tcou", "phase3d-tcou"),
}


def main() -> None:
    hostname = socket.gethostname().split(".", 1)[0]
    frozen = HOSTS.get(hostname)
    if frozen is None:
        raise SystemExit(f"REFUSING: host {hostname!r} is not frozen for Phase 3D")

    database_url = os.environ.get("BF4PS_DATABASE_URL")
    if not database_url:
        raise SystemExit("REFUSING: BF4PS_DATABASE_URL is not set")
    parsed = urlsplit(database_url)
    if parsed.hostname != EXPECTED_DB_HOST or parsed.path.lstrip("/") != EXPECTED_DATABASE:
        raise SystemExit("REFUSING: database URL is not the frozen Phase 3D test target")

    identity = CollectorIdentity(
        collector_uuid=frozen.collector_uuid,
        collector_name=frozen.collector_name,
        hostname=hostname,
        egress_key=frozen.egress_key,
        lane="background",
    )
    engine = create_engine(database_url, pool_pre_ping=True)

    with engine.connect() as conn:
        db = conn.execute(text("SELECT current_database()" )).scalar_one()
        recovery = conn.execute(text("SELECT pg_is_in_recovery()" )).scalar_one()
        revision = conn.execute(text("SELECT version_num FROM alembic_version" )).scalar_one()
        queue = conn.execute(text("""
            SELECT soldier_id, status, attempt_count
            FROM collection_jobs
            WHERE resource = 'detailed' AND lane = 'background'
            ORDER BY job_id
        """)).mappings().all()
        prior = conn.execute(text("""
            SELECT count(*) FROM collection_events
            WHERE collector_uuid = :uuid
              AND resource = 'detailed' AND lane = 'background'
              AND event_type IN ('collection_success', 'collection_failure')
        """), {"uuid": frozen.collector_uuid}).scalar_one()

    if db != EXPECTED_DATABASE or recovery or revision != EXPECTED_REVISION:
        raise SystemExit("REFUSING: database safety boundary failed")
    if not queue:
        raise SystemExit("REFUSING: frozen Phase 3D queue is not armed")
    if any(int(row["soldier_id"]) not in COHORT_IDS for row in queue):
        raise SystemExit("REFUSING: detailed/background queue contains work outside frozen cohort")
    if any(int(row["attempt_count"]) != 0 or row["status"] != "pending" for row in queue):
        raise SystemExit("REFUSING: queue is not pristine pending Phase 3D work")
    if prior:
        raise SystemExit(f"REFUSING: {frozen.collector_name} already has Phase 3D attempt events")

    with engine.begin() as conn:
        control = register_collector(conn, identity=identity, software_version="phase3d-three-host-proof")
    if not control.may_claim:
        raise SystemExit("REFUSING: collector is disabled or drained")

    print("===== BF4PS PHASE 3D THREE-HOST WORKER =====")
    print(f"host:             {hostname}")
    print(f"collector:        {frozen.collector_name}")
    print(f"collector UUID:   {frozen.collector_uuid}")
    print(f"egress gate:      {frozen.egress_key}")
    print(f"request interval: {REQUEST_INTERVAL_SECONDS:.1f}s")
    print(f"local ceiling:    {LOCAL_ATTEMPT_CEILING}")
    print(f"armed queue seen: {len(queue)} frozen job(s)")

    attempted = succeeded = failed = 0
    throttles = []
    try:
        while attempted < LOCAL_ATTEMPT_CEILING:
            with engine.begin() as conn:
                control = heartbeat_collector(conn, collector_uuid=frozen.collector_uuid)
            if not control.may_claim:
                print("operator control stopped new claims")
                break

            outcome = collect_one_detailed_job(
                engine,
                identity=identity,
                request_interval_seconds=REQUEST_INTERVAL_SECONDS,
                lease_seconds=120,
                timeout_seconds=15.0,
                retry_after_seconds=300,
            )
            if outcome is None:
                print("no claimable frozen work remains")
                break

            attempted += 1
            if isinstance(outcome, CollectedJob):
                succeeded += 1
                print(f"[{attempted:02d}/{LOCAL_ATTEMPT_CEILING}] SUCCESS soldier={outcome.soldier_id} job={outcome.job_id} {outcome.platform}")
            elif isinstance(outcome, FailedJob):
                failed += 1
                print(f"[{attempted:02d}/{LOCAL_ATTEMPT_CEILING}] FAILURE soldier={outcome.soldier_id} job={outcome.job_id} {outcome.platform} http={outcome.http_status} class={outcome.error_class}")
                if outcome.http_status in {403, 429} or outcome.error_class == "battlelog_throttle":
                    throttles.append(outcome)
            else:
                raise RuntimeError(f"unexpected collector result {type(outcome)!r}")
    finally:
        with engine.begin() as conn:
            stop_collector(conn, collector_uuid=frozen.collector_uuid)

    with engine.connect() as conn:
        events = conn.execute(text("""
            SELECT soldier_id, attempt_number, result, http_status, error_class, lease_token
            FROM collection_events
            WHERE collector_uuid = :uuid
              AND resource = 'detailed' AND lane = 'background'
              AND event_type IN ('collection_success', 'collection_failure')
            ORDER BY event_id
        """), {"uuid": frozen.collector_uuid}).mappings().all()
        collector = conn.execute(text("""
            SELECT heartbeat_state, enabled, drained, current_job_id
            FROM collectors WHERE collector_uuid = :uuid
        """), {"uuid": frozen.collector_uuid}).mappings().one()
        gate = conn.execute(text("""
            SELECT egress_key, next_request_at, updated_at
            FROM request_gates WHERE egress_key = :key
        """), {"key": frozen.egress_key}).mappings().one_or_none()

    event_soldiers = [int(row["soldier_id"]) for row in events]
    if len(events) != attempted:
        raise RuntimeError("event ledger does not match local attempt count")
    if len(event_soldiers) != len(set(event_soldiers)):
        raise RuntimeError("collector attempted a frozen soldier more than once")
    if any(soldier_id not in COHORT_IDS for soldier_id in event_soldiers):
        raise RuntimeError("collector escaped frozen cohort")
    if collector["heartbeat_state"] != "unknown" or collector["current_job_id"] is not None:
        raise RuntimeError("collector did not stop cleanly")
    if not collector["enabled"] or collector["drained"]:
        raise RuntimeError("runtime changed operator controls")
    if gate is None:
        raise RuntimeError("request gate was not materialized")

    print("\n===== LOCAL VALIDATION =====")
    print(f"attempted:             {attempted}/{LOCAL_ATTEMPT_CEILING}")
    print(f"success / failure:     {succeeded} / {failed}")
    print(f"throttle signals:      {len(throttles)}")
    print("frozen cohort boundary: PASS")
    print("unique local soldiers:  PASS")
    print("request gate exists:    PASS")
    print("collector clean stop:   PASS")
    print("operator controls:      PASS")
    print("PHASE 3D HOST WORKER: PASS")


if __name__ == "__main__":
    main()
