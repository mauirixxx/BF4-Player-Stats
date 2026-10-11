"""Bounded live weapons/vehicles persistence verification on the retained scratch cohort.

Runs existing production collector functions; no schema migration, fleet activation,
or credential output. One allowed attempt per resource, scoped to one known PC soldier.
"""
from __future__ import annotations

import argparse
import os
from sqlalchemy import create_engine, text

from bf4ps.collection_jobs import enqueue_job
from bf4ps.weapon_collector import (
    CollectorIdentity as WeaponIdentity,
    CollectedWeaponJob, FailedWeaponJob, collect_one_weapon_job,
)
from bf4ps.vehicle_collector import (
    CollectorIdentity as VehicleIdentity,
    CollectedVehicleJob, FailedVehicleJob, collect_one_vehicle_job,
)

EXPECTED_DB = "bf4ps_scratch_stage9c_integration"
EXPECTED_ROLE = "bf4ps_stage9c_integration"
EXPECTED_REVISION = "0004_stage9c_supervision_runs"
EXPECTED_COLLECTOR = "live-persistence-validation-tcou"
PERSONA = 236753552
RESOURCES = {
    "weapons": ("weapons_state", "soldier_weapon_stats", "weapon_catalog"),
    "vehicles": ("vehicles_state", "soldier_vehicle_stats", "vehicle_catalog"),
}


def preflight(engine, resource):
    state_column, stats_table, catalog_table = RESOURCES[resource]
    with engine.connect() as conn:
        identity = conn.execute(text(
            "SELECT current_database(),current_user,pg_is_in_recovery(),"
            "current_setting('transaction_read_only')"
        )).one()
        revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        if tuple(identity) != (EXPECTED_DB, EXPECTED_ROLE, False, "off") or revision != EXPECTED_REVISION:
            raise RuntimeError("refusing unexpected DB/role/read-write state/schema revision")
        if conn.execute(text("SELECT count(*) FROM collection_jobs")).scalar_one() != 0:
            raise RuntimeError("refusing nonempty queue")
        if conn.execute(text("SELECT count(*) FROM collectors")).scalar_one() != 1:
            raise RuntimeError("refusing unexpected collector inventory")
        collector = conn.execute(text("""
            SELECT collector_uuid,collector_name,hostname,egress_key,lane,enabled,drained,
                   retired_at,current_job_id FROM collectors WHERE collector_name=:name
        """), {"name": EXPECTED_COLLECTOR}).mappings().one()
        if not (collector["hostname"] == "tcou" and
                collector["egress_key"] == "tcou-live-validation" and
                collector["lane"] == "background" and collector["enabled"] and
                not collector["drained"] and collector["retired_at"] is None and
                collector["current_job_id"] is None):
            raise RuntimeError("refusing unexpected collector state")
        soldiers = conn.execute(text("""
            SELECT soldier_id FROM soldiers WHERE persona_id=:persona AND platform='pc'
        """), {"persona": PERSONA}).scalars().all()
        if len(soldiers) != 1:
            raise RuntimeError("expected exactly one retained test soldier")
        soldier_id = soldiers[0]
        existing_state = conn.execute(text(
            "SELECT " + state_column + " FROM collection_state WHERE soldier_id=:id"
        ), {"id": soldier_id}).scalar_one()
        if existing_state != "never_attempted":
            raise RuntimeError(f"refusing already-attempted resource: {resource}={existing_state}")
        if conn.execute(text(
            "SELECT count(*) FROM " + stats_table + " WHERE soldier_id=:id"
        ), {"id": soldier_id}).scalar_one() != 0:
            raise RuntimeError("refusing existing soldier resource statistics")
        baseline = conn.execute(text("SELECT coalesce(max(event_id),0) FROM collection_events")).scalar_one()
        print(f"PREFLIGHT PASS resource={resource} soldier={soldier_id} "
              f"revision={revision} baseline_event={baseline}", flush=True)
        return collector, soldier_id, baseline


def run(resource):
    engine = create_engine(os.environ["BF4PS_STAGE9C_INTEGRATION_URL"], pool_pre_ping=True)
    collector, soldier_id, baseline = preflight(engine, resource)
    with engine.begin() as conn:
        enqueue_job(conn, soldier_id=soldier_id, resource=resource, lane="background",
                    priority_class="bootstrap", reason="authorized_live_resource_persistence")
    identity_class = WeaponIdentity if resource == "weapons" else VehicleIdentity
    collect = collect_one_weapon_job if resource == "weapons" else collect_one_vehicle_job
    identity = identity_class(
        collector_uuid=collector["collector_uuid"], collector_name=collector["collector_name"],
        hostname=collector["hostname"], egress_key=collector["egress_key"], lane=collector["lane"],
    )
    result = collect(
        engine, identity=identity, request_interval_seconds=10.0,
        allowed_soldier_ids=[soldier_id], max_total_attempts=1,
        attempts_after_event_id=baseline, attempt_ceiling_resources=[resource],
        enforce_production_budget=True, lease_seconds=120, timeout_seconds=30.0,
        retry_after_seconds=3600,
    )
    state_column, stats_table, catalog_table = RESOURCES[resource]
    with engine.connect() as conn:
        state = conn.execute(text(
            "SELECT " + state_column + " FROM collection_state WHERE soldier_id=:id"
        ), {"id": soldier_id}).scalar_one()
        rows = conn.execute(text(
            "SELECT count(*) FROM " + stats_table + " WHERE soldier_id=:id"
        ), {"id": soldier_id}).scalar_one()
        catalog = conn.execute(text("SELECT count(*) FROM " + catalog_table)).scalar_one()
        events = conn.execute(text("""
            SELECT event_type FROM collection_events
            WHERE soldier_id=:id AND resource=:resource AND event_id>:baseline ORDER BY event_id
        """), {"id":soldier_id,"resource":resource,"baseline":baseline}).scalars().all()
        jobs = conn.execute(text(
            "SELECT count(*) FROM collection_jobs WHERE soldier_id=:id AND resource=:resource"
        ), {"id":soldier_id,"resource":resource}).scalar_one()
    print(f"RESULT resource={resource} result={result!r} state={state} "
          f"stat_rows={rows} catalog_rows={catalog} events={events} jobs={jobs}", flush=True)
    if isinstance(result, (CollectedWeaponJob, CollectedVehicleJob)):
        assert state == "success" and jobs == 0
        assert events == ["collection_attempt_started", "collection_success"]
        assert rows == (result.weapon_rows if resource == "weapons" else result.vehicle_rows)
        assert rows > 0 and catalog >= rows
        print(f"LIVE {resource.upper()} PERSISTENCE PASS",flush=True)
    elif isinstance(result, (FailedWeaponJob, FailedVehicleJob)):
        print("Live resource fetch failed; failure recorded; no automatic retry",flush=True)
        raise SystemExit(2)
    else:
        raise RuntimeError("no job claimed; inspect budget and queue before retry")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--resource", required=True, choices=tuple(RESOURCES))
    args = parser.parse_args()
    run(args.resource)
