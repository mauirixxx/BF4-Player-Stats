"""D2-only real weapon/vehicle persistence lease reclaim, no HTTP."""
from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import create_engine, text

from bf4ps.collection_jobs import claim_next_job, enqueue_job, mark_job_running
from bf4ps.battlelog_weapons import NormalizedWeaponStat
from bf4ps.battlelog_vehicles import NormalizedVehicleStat
from decimal import Decimal
from bf4ps.weapon_persistence import persist_weapon_success
from bf4ps.vehicle_persistence import persist_vehicle_success
from bf4ps.distributed_duplicate_events import record_discarded_duplicate
from scripts.phase5b_stage9c_d2_ledger_integration import (
    EXPECTED_DB, EXPECTED_IP, EXPECTED_USER, HEAD, validate_target,
)


def run(url: str, resource: str) -> None:
    if resource not in ('weapons', 'vehicles'):
        raise ValueError('unsupported resource')
    validate_target(url)
    engine = create_engine(url, connect_args={"connect_timeout": 5})
    marker = "synthetic-" + resource + "-race-" + uuid4().hex
    collectors = [uuid4(), uuid4()]
    soldier_id = None
    try:
        with engine.connect() as conn:
            row = conn.execute(text(
                "SELECT current_database(),current_user,inet_server_addr(),"
                "pg_is_in_recovery(),current_setting('transaction_read_only')"
            )).one()
            if (row[0], row[1], str(row[2]), row[3], row[4]) != (
                EXPECTED_DB, EXPECTED_USER, EXPECTED_IP, False, "off"
            ):
                raise RuntimeError("REFUSING unexpected D2 database identity")
            if conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() != HEAD:
                raise RuntimeError("REFUSING unexpected migration")
            if any(conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
                   for table in ("soldiers", "collection_events", "collection_jobs", "collectors")):
                raise RuntimeError("REFUSING nonempty D2 core tables")
            conn.rollback()

        with engine.begin() as conn:
            soldier_id = conn.execute(text("""
                INSERT INTO soldiers (persona_id,platform,current_name,first_seen_at,last_seen_at)
                VALUES (:persona,'pc',:name,clock_timestamp(),clock_timestamp())
                RETURNING soldier_id
            """), {"persona": 1_800_000_000 + uuid4().int % 100_000_000,
                   "name": marker}).scalar_one()
            for idx, uid in enumerate(collectors):
                conn.execute(text("""
                    INSERT INTO collectors (collector_uuid,collector_name,hostname,lane,egress_key)
                    VALUES (:uuid,:name,'tcou','background',:egress)
                """), {"uuid": uid, "name": marker + str(idx), "egress": marker + str(idx)})
            job_id = enqueue_job(conn, soldier_id=soldier_id, resource=resource,
                                 lane="background", priority_class="bootstrap", reason=marker)

        with engine.begin() as conn:
            loser = claim_next_job(conn, collector_uuid=collectors[0],
                                   resource=resource, lane="background", lease_seconds=120)
            assert loser and loser.job_id == job_id and mark_job_running(conn, loser)
            # Deliberately expire the first lease; the second collector reclaims.
            conn.execute(text("""
                UPDATE collection_jobs SET lease_expires_at=clock_timestamp()-interval '1 second'
                WHERE job_id=:job_id
            """), {"job_id": job_id})
        with engine.begin() as conn:
            winner = claim_next_job(conn, collector_uuid=collectors[1],
                                    resource=resource, lane="background", lease_seconds=120)
            assert winner and winner.job_id == job_id and mark_job_running(conn, winner)

        persist = persist_weapon_success if resource == "weapons" else persist_vehicle_success
        if resource == "weapons":
            payload = {"weapons": [NormalizedWeaponStat(
                weapon_guid=marker, name="Synthetic Weapon", slug="synthetic-weapon",
                category="assault", kills=3, headshots=1, shots_fired=30,
                shots_hit=12, time_equipped_seconds=120,
            )]}
        else:
            payload = {"vehicles": [NormalizedVehicleStat(
                vehicle_guid=marker, name="Synthetic Vehicle", slug="synthetic-vehicle",
                category="armor", kills=2, time_in_seconds=90,
                destroy_x_in_y=Decimal("4"),
            )]}
        with engine.begin() as conn:
            assert persist(
                conn, job=winner, **payload, source_fetched_at=datetime.now(timezone.utc),
                persona_id=1, platform="pc", collector_name=marker + "1",
                hostname="tcou", egress_key=marker + "1", duration_ms=5, response_bytes=0,
            ) == 1

        try:
            with engine.begin() as conn:
                persist(
                    conn, job=loser, **payload, source_fetched_at=datetime.now(timezone.utc),
                    persona_id=1, platform="pc", collector_name=marker + "0",
                    hostname="tcou", egress_key=marker + "0", duration_ms=5, response_bytes=0,
                )
        except RuntimeError as exc:
            if str(exc) != ("weapon" if resource == "weapons" else "vehicle") + " success rejected: job lease is no longer owned":
                raise
        else:
            raise AssertionError("stale collector incorrectly persisted")

        with engine.begin() as conn:
            assert record_discarded_duplicate(
                conn, job=loser, persona_id=1, platform="pc",
                collector_name=marker + "0", hostname="tcou", egress_key=marker + "0",
                duration_ms=5, http_status=200,
            )
        with engine.connect() as conn:
            counts = [
                conn.execute(text(f"SELECT count(*) FROM {table} WHERE soldier_id=:s"),
                             {"s": soldier_id}).scalar_one()
                for table in (("soldier_weapon_stats",) if resource == "weapons" else ("soldier_vehicle_stats",))
            ]
            success = conn.execute(text("""
                SELECT count(*) FROM collection_events
                WHERE soldier_id=:s AND event_type='collection_success'
            """), {"s": soldier_id}).scalar_one()
            discarded = conn.execute(text("""
                SELECT count(*) FROM collection_events
                WHERE soldier_id=:s AND event_type='collection_duplicate_discarded'
            """), {"s": soldier_id}).scalar_one()
            remaining = conn.execute(text("""
                SELECT count(*) FROM collection_jobs WHERE soldier_id=:s
            """), {"s": soldier_id}).scalar_one()
            conn.rollback()
        assert counts == [1] and success == 1 and discarded == 1 and remaining == 0, (
            counts, success, discarded, remaining
        )
        print(f"PASS: real {resource} persistence winner 1, stale loser rejected, duplicate 1, job 0")
        print("LIMIT: deterministic lease-reclaim interleaving, not simultaneous physical HTTP")
    finally:
        try:
            if soldier_id is not None:
                with engine.begin() as conn:
                    conn.execute(text("DELETE FROM collection_events WHERE soldier_id=:s"),
                                 {"s": soldier_id})
                    conn.execute(text("DELETE FROM soldiers WHERE soldier_id=:s AND current_name=:name"),
                                 {"s": soldier_id, "name": marker})
                    if resource == "weapons":
                        conn.execute(text("DELETE FROM weapon_catalog WHERE weapon_guid=:marker"), {"marker": marker})
                    else:
                        conn.execute(text("DELETE FROM vehicle_catalog WHERE vehicle_guid=:marker"), {"marker": marker})
                    conn.execute(text("DELETE FROM collectors WHERE collector_uuid IN (:a,:b)"),
                                 {"a": collectors[0], "b": collectors[1]})
        finally:
            engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        parser.error("--execute required")
    url = os.environ.get("BF4PS_STAGE9C_D2_URL")
    if not url:
        parser.error("BF4PS_STAGE9C_D2_URL required")
    for resource in ("weapons", "vehicles"):
        run(url, resource)
