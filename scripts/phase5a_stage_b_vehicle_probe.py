#!/usr/bin/env python3
"""Guarded one-soldier Stage B vehicle lifecycle probe."""
from __future__ import annotations

import socket

from sqlalchemy import text

from bf4ps.collection_jobs import enqueue_job
from bf4ps.collector_runtime import register_collector, stop_collector
from bf4ps.db import make_engine
from bf4ps.vehicle_collector import CollectorIdentity, CollectedVehicleJob, FailedVehicleJob, collect_one_vehicle_job
from phase5a_stage_a_common import HOSTS, REQUEST_INTERVAL_SECONDS, LEASE_SECONDS, assert_target

SOLDIER_ID = 15
EXPECTED_PERSONA_ID = 513446234
EXPECTED_PLATFORM = "pc"
EXPECTED_NAME = "jdisa35w"
PROBE_EVENT_TYPE = "phase5a_stage_b_vehicle_probe_started"
JOB_REASON = "phase5a_stage_b_vehicle_probe"
SOFTWARE_VERSION = "phase5a-stage-b-vehicle-probe"


def main() -> int:
    host = socket.gethostname().split(".", 1)[0]
    if host != "tcou":
        raise SystemExit(f"REFUSING: probe must run on tcou, not {host!r}")
    frozen = HOSTS[host]
    engine = make_engine()

    print("===== BF4PS PHASE 5A STAGE B SINGLE VEHICLE LIFECYCLE PROBE =====")
    print("maximum Battlelog requests: 1")

    with engine.begin() as conn:
        assert_target(conn)
        soldier = conn.execute(text("""
            SELECT soldier_id, persona_id, platform, current_name
            FROM soldiers WHERE soldier_id=:soldier_id
        """), {"soldier_id": SOLDIER_ID}).mappings().one()
        if (int(soldier["persona_id"]), str(soldier["platform"]), str(soldier["current_name"])) != (
            EXPECTED_PERSONA_ID, EXPECTED_PLATFORM, EXPECTED_NAME
        ):
            raise RuntimeError(f"frozen soldier identity mismatch: {dict(soldier)}")

        foreign = int(conn.execute(text("""
            SELECT count(*) FROM collection_jobs
            WHERE lane='background'
        """)).scalar_one())
        if foreign:
            raise RuntimeError(f"background queue is not empty: {foreign} job(s)")

        state = conn.execute(text("""
            SELECT weapons_state, vehicles_state, vehicles_last_attempt_at,
                   vehicles_last_success_at, vehicles_next_due_at,
                   vehicles_consecutive_failures, vehicles_last_error_class,
                   vehicles_last_error_message
            FROM collection_state WHERE soldier_id=:soldier_id
        """), {"soldier_id": SOLDIER_ID}).mappings().one()
        weapon_rows = int(conn.execute(text("""
            SELECT count(*) FROM soldier_weapon_stats WHERE soldier_id=:soldier_id
        """), {"soldier_id": SOLDIER_ID}).scalar_one())
        vehicle_rows = int(conn.execute(text("""
            SELECT count(*) FROM soldier_vehicle_stats WHERE soldier_id=:soldier_id
        """), {"soldier_id": SOLDIER_ID}).scalar_one())
        prior_probe = int(conn.execute(text("""
            SELECT count(*) FROM collection_events
            WHERE event_type=:event_type AND soldier_id=:soldier_id
        """), {"event_type": PROBE_EVENT_TYPE, "soldier_id": SOLDIER_ID}).scalar_one())

        if state["weapons_state"] != "success" or weapon_rows <= 0:
            raise RuntimeError(
                f"accepted Stage A weapon state not present: state={state['weapons_state']} rows={weapon_rows}"
            )
        pristine = (
            state["vehicles_state"] == "never_attempted"
            and state["vehicles_last_attempt_at"] is None
            and state["vehicles_last_success_at"] is None
            and state["vehicles_next_due_at"] is None
            and int(state["vehicles_consecutive_failures"]) == 0
            and state["vehicles_last_error_class"] is None
            and state["vehicles_last_error_message"] is None
            and vehicle_rows == 0
        )
        if not pristine:
            raise RuntimeError(f"vehicle state is not pristine: state={dict(state)} rows={vehicle_rows}")
        if prior_probe:
            raise RuntimeError(f"probe already exists for soldier {SOLDIER_ID}: {prior_probe}")

        identity = CollectorIdentity(
            frozen.collector_uuid, frozen.collector_name, host, frozen.egress_key, "background"
        )
        control = register_collector(conn, identity=identity, software_version=SOFTWARE_VERSION)
        if not control.enabled or control.drained:
            raise RuntimeError(f"tcou collector unavailable: enabled={control.enabled} drained={control.drained}")

        marker = conn.execute(text("""
            INSERT INTO collection_events
                (collector_uuid, collector_name_snapshot, hostname_snapshot,
                 egress_key_snapshot, soldier_id, persona_id, platform, resource,
                 lane, event_type, result, metadata)
            VALUES
                (:collector_uuid, :collector_name, :hostname, :egress_key,
                 :soldier_id, :persona_id, :platform, 'vehicles',
                 'background', :event_type, 'probe_boundary',
                 jsonb_build_object('max_physical_attempts', 1))
            RETURNING event_id
        """), {
            "collector_uuid": frozen.collector_uuid,
            "collector_name": frozen.collector_name,
            "hostname": host,
            "egress_key": frozen.egress_key,
            "soldier_id": SOLDIER_ID,
            "persona_id": EXPECTED_PERSONA_ID,
            "platform": EXPECTED_PLATFORM,
            "event_type": PROBE_EVENT_TYPE,
        }).scalar_one()

        job_id = enqueue_job(
            conn, soldier_id=SOLDIER_ID, resource="vehicles", lane="background",
            priority_class="bootstrap", reason=JOB_REASON, priority_value=1_000_001,
        )

    print(f"probe boundary event_id={marker} job_id={job_id}")
    try:
        outcome = collect_one_vehicle_job(
            engine,
            identity=identity,
            request_interval_seconds=REQUEST_INTERVAL_SECONDS,
            lease_seconds=LEASE_SECONDS,
            timeout_seconds=30,
            retry_after_seconds=86400,
            allowed_soldier_ids=(SOLDIER_ID,),
            max_total_attempts=1,
            attempts_after_event_id=int(marker),
        )
        if outcome is None:
            raise RuntimeError("probe collector did not claim the seeded vehicle job")
        if isinstance(outcome, CollectedVehicleJob):
            print(
                f"SUCCESS soldier={outcome.soldier_id} job={outcome.job_id} "
                f"platform={outcome.platform} rows={outcome.vehicle_rows} "
                f"bytes={outcome.response_bytes} duration_ms={outcome.duration_ms}"
            )
        elif isinstance(outcome, FailedVehicleJob):
            print(
                f"FAILURE soldier={outcome.soldier_id} job={outcome.job_id} "
                f"platform={outcome.platform} http={outcome.http_status} "
                f"class={outcome.error_class} duration_ms={outcome.duration_ms}"
            )
    finally:
        with engine.begin() as conn:
            stop_collector(conn, collector_uuid=frozen.collector_uuid)

    print("PHASE 5A STAGE B SINGLE VEHICLE LIFECYCLE PROBE: COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
