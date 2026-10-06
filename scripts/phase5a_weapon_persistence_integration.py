#!/usr/bin/env python3
"""Rollback-only PostgreSQL integration test for Phase 5A weapon persistence."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import text

from bf4ps.battlelog_weapons import NormalizedWeaponStat
from bf4ps.collection_jobs import claim_next_job, enqueue_job, mark_job_running
from bf4ps.db import make_engine
from bf4ps.weapon_persistence import persist_weapon_success

EXPECTED_DATABASE = "bf4_playerstats_test"
EXPECTED_REVISION = "0003_request_gates"
COLLECTOR_UUID = UUID("b2b3ef60-62e8-4d4a-91b0-41a2e2a3e05a")
COLLECTOR_NAME = "phase5a-weapon-integration"
HOSTNAME = "phase5a-integration"
EGRESS_KEY = "phase5a-integration"
PERSONA_ID = 9_999_999_999_951
PLATFORM = "pc"
SOLDIER_NAME = "BF4PS_PHASE5A_SYNTHETIC"


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    suffix = f"  {detail}" if detail else ""
    print(f"{label:<68} {status}{suffix}")
    if not condition:
        raise AssertionError(f"{label}: {detail or 'condition was false'}")


def assert_target(conn) -> None:
    row = conn.execute(text("""
        SELECT current_database() AS database_name,
               pg_is_in_recovery() AS recovery,
               current_setting('transaction_read_only') AS read_only
    """)).mappings().one()
    revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    check("target database is bf4_playerstats_test", row["database_name"] == EXPECTED_DATABASE, str(row["database_name"]))
    check("target is writable primary", not row["recovery"] and row["read_only"] == "off", f"recovery={row['recovery']} read_only={row['read_only']}")
    check("Alembic revision is frozen Phase 5A revision", revision == EXPECTED_REVISION, str(revision))


def weapon(
    guid: str,
    name: str,
    slug: str,
    category: str,
    *,
    kills: int,
    headshots: int,
    shots_fired: int,
    shots_hit: int,
    time_equipped_seconds: int,
) -> NormalizedWeaponStat:
    return NormalizedWeaponStat(
        weapon_guid=guid,
        name=name,
        slug=slug,
        category=category,
        kills=kills,
        headshots=headshots,
        shots_fired=shots_fired,
        shots_hit=shots_hit,
        time_equipped_seconds=time_equipped_seconds,
    )


def create_fixture(conn) -> int:
    now = datetime.now(timezone.utc)
    soldier_id = int(conn.execute(text("""
        INSERT INTO soldiers
            (persona_id, platform, current_name, first_seen_at, last_seen_at)
        VALUES
            (:persona_id, :platform, :name, :now, :now)
        RETURNING soldier_id
    """), {"persona_id": PERSONA_ID, "platform": PLATFORM, "name": SOLDIER_NAME, "now": now}).scalar_one())
    conn.execute(text("""
        INSERT INTO collectors
            (collector_uuid, collector_name, hostname, lane, egress_key,
             enabled, drained, heartbeat_state)
        VALUES
            (:uuid, :name, :hostname, 'background', :egress, true, false, 'healthy')
    """), {"uuid": COLLECTOR_UUID, "name": COLLECTOR_NAME, "hostname": HOSTNAME, "egress": EGRESS_KEY})
    return soldier_id


def start_job(conn, soldier_id: int):
    job_id = enqueue_job(
        conn,
        soldier_id=soldier_id,
        resource="weapons",
        lane="background",
        priority_class="bootstrap",
        reason="phase5a_weapon_persistence_integration",
    )
    job = claim_next_job(
        conn,
        collector_uuid=COLLECTOR_UUID,
        lane="background",
        resource="weapons",
        lease_seconds=600,
        allowed_soldier_ids=[soldier_id],
    )
    check("queued weapon job was claimed", job is not None, f"job_id={job_id}")
    assert job is not None
    check("claimed expected queue job", job.job_id == job_id, f"claimed={job.job_id} expected={job_id}")
    check("claimed job transitioned to running", mark_job_running(conn, job), f"job_id={job.job_id}")
    return job


def soldier_rows(conn, soldier_id: int):
    return conn.execute(text("""
        SELECT wc.weapon_guid, wc.name, wc.slug, wc.category,
               sws.kills, sws.headshots, sws.shots_fired, sws.shots_hit,
               sws.time_equipped_seconds, sws.source_fetched_at
        FROM soldier_weapon_stats sws
        JOIN weapon_catalog wc ON wc.weapon_id = sws.weapon_id
        WHERE sws.soldier_id = :soldier_id
        ORDER BY wc.weapon_guid
    """), {"soldier_id": soldier_id}).mappings().all()


def main() -> int:
    print("===== BF4PS PHASE 5A WEAPON PERSISTENCE INTEGRATION =====")
    print("mode: real PostgreSQL / synthetic data / outer transaction rollback")
    print("Battlelog requests: 0")
    engine = make_engine()
    conn = engine.connect()
    outer = conn.begin()
    try:
        assert_target(conn)
        soldier_id = create_fixture(conn)
        print(f"synthetic soldier_id: {soldier_id}")

        first_payload = [
            weapon("PHASE5A-WPN-A", "Synthetic A", "synthetic-a", "Assault Rifles", kills=10, headshots=2, shots_fired=100, shots_hit=25, time_equipped_seconds=60),
            weapon("PHASE5A-WPN-B", "Synthetic B", "synthetic-b", "Carbines", kills=20, headshots=4, shots_fired=200, shots_hit=50, time_equipped_seconds=120),
        ]
        first_job = start_job(conn, soldier_id)
        first_at = datetime.now(timezone.utc)
        persisted = persist_weapon_success(
            conn,
            job=first_job,
            weapons=first_payload,
            source_fetched_at=first_at,
            persona_id=PERSONA_ID,
            platform=PLATFORM,
            collector_name=COLLECTOR_NAME,
            hostname=HOSTNAME,
            egress_key=EGRESS_KEY,
            duration_ms=123,
            response_bytes=4567,
        )
        print("\n===== CASE 1 — INITIAL SUCCESS =====")
        check("persistence returned two current rows", persisted == 2, str(persisted))
        rows = soldier_rows(conn, soldier_id)
        check("two soldier weapon rows persisted", len(rows) == 2, str(len(rows)))
        check("initial retained counters are exact", [(r["weapon_guid"], r["kills"], r["headshots"], r["shots_fired"], r["shots_hit"], r["time_equipped_seconds"]) for r in rows] == [("PHASE5A-WPN-A", 10, 2, 100, 25, 60), ("PHASE5A-WPN-B", 20, 4, 200, 50, 120)])
        state = conn.execute(text("""
            SELECT weapons_state, weapons_last_attempt_at, weapons_last_success_at,
                   weapons_next_due_at, weapons_consecutive_failures,
                   weapons_last_error_class, weapons_last_error_message
            FROM collection_state WHERE soldier_id=:soldier_id
        """), {"soldier_id": soldier_id}).mappings().one()
        check("weapon collection state converged to success", state["weapons_state"] == "success")
        check("weapon failure state is cleared", state["weapons_consecutive_failures"] == 0 and state["weapons_last_error_class"] is None and state["weapons_last_error_message"] is None and state["weapons_next_due_at"] is None)
        check("first completed queue job was deleted", conn.execute(text("SELECT count(*) FROM collection_jobs WHERE job_id=:job_id"), {"job_id": first_job.job_id}).scalar_one() == 0)
        first_event = conn.execute(text("""
            SELECT event_type, result, job_id, soldier_id, lease_token, metadata
            FROM collection_events
            WHERE job_id=:job_id AND resource='weapons'
        """), {"job_id": first_job.job_id}).mappings().one()
        check("first success event identity is exact", first_event["event_type"] == "collection_success" and first_event["result"] == "success" and first_event["soldier_id"] == soldier_id and first_event["lease_token"] == first_job.lease_token)
        check("first success event records cost metadata", first_event["metadata"] == {"weapon_rows": 2, "response_bytes": 4567}, str(first_event["metadata"]))

        second_payload = [
            replace(first_payload[0], name="Synthetic A Updated", kills=99, headshots=9, shots_fired=999, shots_hit=333, time_equipped_seconds=777),
            weapon("PHASE5A-WPN-C", "Synthetic C", "synthetic-c", "LMGs", kills=30, headshots=6, shots_fired=300, shots_hit=75, time_equipped_seconds=180),
        ]
        second_job = start_job(conn, soldier_id)
        second_at = first_at + timedelta(seconds=30)
        persist_weapon_success(
            conn,
            job=second_job,
            weapons=second_payload,
            source_fetched_at=second_at,
            persona_id=PERSONA_ID,
            platform=PLATFORM,
            collector_name=COLLECTOR_NAME,
            hostname=HOSTNAME,
            egress_key=EGRESS_KEY,
            duration_ms=234,
            response_bytes=5678,
        )
        print("\n===== CASE 2 — AUTHORITATIVE REPLACEMENT =====")
        rows = soldier_rows(conn, soldier_id)
        by_guid = {r["weapon_guid"]: r for r in rows}
        check("replacement leaves exactly two current rows", len(rows) == 2, str(len(rows)))
        check("replacement current set is A + C", set(by_guid) == {"PHASE5A-WPN-A", "PHASE5A-WPN-C"}, str(sorted(by_guid)))
        check("retained weapon counters were replaced", by_guid["PHASE5A-WPN-A"]["kills"] == 99 and by_guid["PHASE5A-WPN-A"]["shots_fired"] == 999)
        check("retained catalog metadata follows latest observation", by_guid["PHASE5A-WPN-A"]["name"] == "Synthetic A Updated")
        catalog_guids = set(conn.execute(text("SELECT weapon_guid FROM weapon_catalog WHERE weapon_guid LIKE 'PHASE5A-WPN-%'")).scalars())
        check("global catalog retains all three observed GUIDs", catalog_guids == {"PHASE5A-WPN-A", "PHASE5A-WPN-B", "PHASE5A-WPN-C"}, str(sorted(catalog_guids)))
        event_count = int(conn.execute(text("SELECT count(*) FROM collection_events WHERE soldier_id=:soldier_id AND resource='weapons' AND event_type='collection_success'"), {"soldier_id": soldier_id}).scalar_one())
        check("two durable success events exist", event_count == 2, str(event_count))
        check("second completed queue job was deleted", conn.execute(text("SELECT count(*) FROM collection_jobs WHERE job_id=:job_id"), {"job_id": second_job.job_id}).scalar_one() == 0)

        third_job = start_job(conn, soldier_id)
        before_fence = [(r["weapon_guid"], r["kills"]) for r in soldier_rows(conn, soldier_id)]
        print("\n===== CASE 3 — STALE-OWNER FENCING =====")
        savepoint = conn.begin_nested()
        try:
            conn.execute(text("UPDATE collection_jobs SET lease_token=:replacement WHERE job_id=:job_id"), {"replacement": uuid4(), "job_id": third_job.job_id})
            rejected = False
            try:
                persist_weapon_success(
                    conn,
                    job=third_job,
                    weapons=[replace(second_payload[0], kills=123456)],
                    source_fetched_at=second_at + timedelta(seconds=30),
                    persona_id=PERSONA_ID,
                    platform=PLATFORM,
                    collector_name=COLLECTOR_NAME,
                    hostname=HOSTNAME,
                    egress_key=EGRESS_KEY,
                    duration_ms=345,
                    response_bytes=6789,
                )
            except RuntimeError as exc:
                rejected = "lease is no longer owned" in str(exc)
                print(f"expected rejection: {exc}")
            check("stale lease token is rejected", rejected)
            after_fence = [(r["weapon_guid"], r["kills"]) for r in soldier_rows(conn, soldier_id)]
            check("stale owner cannot mutate current weapon rows", after_fence == before_fence, str(after_fence))
        finally:
            savepoint.rollback()

        check("original third-job ownership restored by savepoint rollback", conn.execute(text("SELECT lease_token FROM collection_jobs WHERE job_id=:job_id"), {"job_id": third_job.job_id}).scalar_one() == third_job.lease_token)

        print("\n===== ACCEPTANCE =====")
        print("initial persistence transaction shape                               PASS")
        print("authoritative replacement semantics                               PASS")
        print("stale-owner fencing                                               PASS")
        print("Battlelog requests                                                0")
        print("committed database writes                                         0 (outer rollback)")
        print("PHASE 5A WEAPON PERSISTENCE INTEGRATION: PASS")
        return 0
    finally:
        if outer.is_active:
            outer.rollback()
        conn.close()
        engine.dispose()
        print("outer transaction: ROLLED BACK")


if __name__ == "__main__":
    raise SystemExit(main())
