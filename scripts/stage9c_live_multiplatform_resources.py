"""Run four bounded live weapon/vehicle jobs for the verified PS4/Xbox cohort.

Dedicated Stage 9C integration DB only, two known soldiers, four attempts max.
Existing production admission and egress pacing; no worker fleet activation.
"""
from __future__ import annotations

import os
from sqlalchemy import create_engine, text
from bf4ps.collection_jobs import enqueue_job
from bf4ps.weapon_collector import (
    CollectorIdentity as WeaponIdentity, CollectedWeaponJob, FailedWeaponJob, collect_one_weapon_job,
)
from bf4ps.vehicle_collector import (
    CollectorIdentity as VehicleIdentity, CollectedVehicleJob, FailedVehicleJob, collect_one_vehicle_job,
)

COHORT = (("ps4", 303498475), ("xboxone", 928420744))
RESOURCES = ("weapons", "vehicles")
EXPECTED_COLLECTOR = "live-persistence-validation-tcou"
EXPECTED_DB = "bf4ps_scratch_stage9c_integration"
EXPECTED_ROLE = "bf4ps_stage9c_integration"
EXPECTED_REVISION = "0004_stage9c_supervision_runs"
STAT_TABLES = {"weapons": ("soldier_weapon_stats", "weapon_catalog"),
               "vehicles": ("soldier_vehicle_stats", "vehicle_catalog")}


def preflight(engine):
    with engine.connect() as conn:
        dbinfo = conn.execute(text(
            "SELECT current_database(),current_user,pg_is_in_recovery(),"
            "current_setting('transaction_read_only')"
        )).one()
        revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        if tuple(dbinfo) != (EXPECTED_DB, EXPECTED_ROLE, False, "off") or revision != EXPECTED_REVISION:
            raise RuntimeError("unexpected database/role/read-only state/revision")
        if conn.execute(text("SELECT count(*) FROM collection_jobs")).scalar_one() != 0:
            raise RuntimeError("queue must be empty before this one-off cohort")
        if conn.execute(text("SELECT count(*) FROM collectors")).scalar_one() != 1:
            raise RuntimeError("unexpected collector inventory")
        collector = conn.execute(text("""
            SELECT collector_uuid,collector_name,hostname,egress_key,lane,enabled,drained,
                   retired_at,current_job_id FROM collectors WHERE collector_name=:name
        """), {"name":EXPECTED_COLLECTOR}).mappings().one()
        if not (collector["hostname"] == "tcou" and
                collector["egress_key"] == "tcou-live-validation" and
                collector["lane"] == "background" and collector["enabled"] and
                not collector["drained"] and collector["retired_at"] is None and
                collector["current_job_id"] is None):
            raise RuntimeError("unexpected collector state")
        soldiers = {}
        for platform, persona in COHORT:
            row = conn.execute(text("""
                SELECT s.soldier_id,cs.detailed_state,cs.weapons_state,cs.vehicles_state
                FROM soldiers s JOIN collection_state cs USING(soldier_id)
                WHERE s.platform=:platform AND s.persona_id=:persona
            """), {"platform":platform,"persona":persona}).mappings().one()
            if (row["detailed_state"],row["weapons_state"],row["vehicles_state"]) != (
                "success","never_attempted","never_attempted"
            ):
                raise RuntimeError(f"resource state is not pristine for {platform}")
            for resource in RESOURCES:
                table, _ = STAT_TABLES[resource]
                if conn.execute(text("SELECT count(*) FROM "+table+" WHERE soldier_id=:id"),
                                {"id":row["soldier_id"]}).scalar_one() != 0:
                    raise RuntimeError(f"resource rows already exist for {platform}/{resource}")
            soldiers[(platform,persona)] = row["soldier_id"]
        baseline = conn.execute(text(
            "SELECT coalesce(max(event_id),0) FROM collection_events"
        )).scalar_one()
        before = {r: conn.execute(text("SELECT count(*) FROM "+STAT_TABLES[r][1])).scalar_one()
                  for r in RESOURCES}
    print(f"PREFLIGHT PASS db={EXPECTED_DB} revision={revision} "
          f"cohort={len(soldiers)} resources=2 max_attempts=4 catalog_before={before}",flush=True)
    return collector, soldiers, baseline, before


def main():
    engine = create_engine(os.environ["BF4PS_STAGE9C_INTEGRATION_URL"], pool_pre_ping=True)
    collector, soldiers, baseline, catalog_before = preflight(engine)
    with engine.begin() as conn:
        for resource in RESOURCES:
            for soldier_id in soldiers.values():
                enqueue_job(conn, soldier_id=soldier_id, resource=resource,
                            lane="background",priority_class="bootstrap",
                            reason="authorized_live_multiplatform_resource_validation")
    identities = {
        "weapons": WeaponIdentity(collector_uuid=collector["collector_uuid"],
                                  collector_name=collector["collector_name"],
                                  hostname=collector["hostname"],
                                  egress_key=collector["egress_key"],lane="background"),
        "vehicles": VehicleIdentity(collector_uuid=collector["collector_uuid"],
                                    collector_name=collector["collector_name"],
                                    hostname=collector["hostname"],
                                    egress_key=collector["egress_key"],lane="background"),
    }
    collect = {"weapons": collect_one_weapon_job, "vehicles": collect_one_vehicle_job}
    results = []
    for resource in RESOURCES:
        for index in range(len(soldiers)):
            result = collect[resource](
                engine, identity=identities[resource], request_interval_seconds=10.0,
                allowed_soldier_ids=list(soldiers.values()), max_total_attempts=4,
                attempts_after_event_id=baseline,attempt_ceiling_resources=list(RESOURCES),
                enforce_production_budget=True,lease_seconds=120,timeout_seconds=30.0,
                retry_after_seconds=3600,
            )
            print(f"COLLECT {resource} {index+1}: {result!r}",flush=True)
            results.append((resource,result))
            if result is None or isinstance(result,(FailedWeaponJob,FailedVehicleJob)):
                raise RuntimeError("resource collection incomplete; inspect durable events and queue")
    with engine.connect() as conn:
        for (platform,persona),soldier_id in soldiers.items():
            for resource in RESOURCES:
                table,catalog_table = STAT_TABLES[resource]
                state = conn.execute(text(
                    "SELECT "+resource+"_state FROM collection_state WHERE soldier_id=:id"
                ),{"id":soldier_id}).scalar_one()
                count = conn.execute(text(
                    "SELECT count(*) FROM "+table+" WHERE soldier_id=:id"
                ),{"id":soldier_id}).scalar_one()
                events = conn.execute(text("""
                    SELECT event_type FROM collection_events
                    WHERE soldier_id=:id AND resource=:resource AND event_id>:baseline
                    ORDER BY event_id
                """),{"id":soldier_id,"resource":resource,"baseline":baseline}).scalars().all()
                jobs = conn.execute(text("""
                    SELECT count(*) FROM collection_jobs
                    WHERE soldier_id=:id AND resource=:resource
                """),{"id":soldier_id,"resource":resource}).scalar_one()
                print(f"VERIFY platform={platform} resource={resource} "
                      f"rows={count} state={state} events={events} jobs={jobs}",flush=True)
                assert state=="success" and count>0 and jobs==0
                assert events==["collection_attempt_started","collection_success"]
        for resource in RESOURCES:
            catalog = conn.execute(text(
                "SELECT count(*) FROM "+STAT_TABLES[resource][1]
            )).scalar_one()
            print(f"CATALOG {resource} before={catalog_before[resource]} after={catalog}",flush=True)
            assert catalog>=catalog_before[resource]
    assert len(results)==4
    assert all(isinstance(r,CollectedWeaponJob if resource=="weapons" else CollectedVehicleJob)
               for resource,r in results)
    print("MULTIPLATFORM WEAPON+VEHICLE PERSISTENCE PASS",flush=True)


if __name__=="__main__":
    main()
