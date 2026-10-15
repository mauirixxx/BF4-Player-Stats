"""Atomic persistence for successful BF4 weapon-statistics collection."""

from __future__ import annotations

from datetime import datetime
from typing import Sequence

from sqlalchemy import text

from bf4ps.bulk_values import bulk_values
from sqlalchemy.engine import Connection

from bf4ps.battlelog_weapons import NormalizedWeaponStat
from bf4ps.collection_jobs import ClaimedJob


def _validate_weapons(weapons: Sequence[NormalizedWeaponStat]) -> None:
    seen: set[str] = set()
    for weapon in weapons:
        if weapon.weapon_guid in seen:
            raise ValueError(f"duplicate weapon_guid: {weapon.weapon_guid!r}")
        seen.add(weapon.weapon_guid)


def persist_weapon_success(
    conn: Connection,
    *,
    job: ClaimedJob,
    weapons: Sequence[NormalizedWeaponStat],
    source_fetched_at: datetime,
    persona_id: int,
    platform: str,
    collector_name: str,
    hostname: str,
    egress_key: str,
    duration_ms: int,
    response_bytes: int,
    http_status: int = 200,
) -> int:
    """Persist one successful weapon fetch and finalize its owned queue job.

    The caller owns the transaction. Catalog reconciliation, replacement of the
    soldier's current weapon rows, collection state, event ledger entry, and
    queue finalization all use the same Connection and therefore commit or roll
    back together.

    Returns the number of current weapon rows persisted for the soldier.
    """
    if job.resource != "weapons":
        raise ValueError("persist_weapon_success requires a weapons job")
    if duration_ms < 0:
        raise ValueError("duration_ms must be non-negative")
    if response_bytes < 0:
        raise ValueError("response_bytes must be non-negative")
    if not 100 <= http_status <= 599:
        raise ValueError("http_status must be between 100 and 599")
    _validate_weapons(weapons)

    # Every successful weapon payload reconciles the same small global catalog.
    # Serialize that shared critical section across collectors so concurrent
    # transactions cannot acquire overlapping unique-index/catalog locks in
    # conflicting orders. The lock is transaction-scoped and releases on
    # commit/rollback.
    conn.execute(
        text("SELECT pg_advisory_xact_lock(hashtext('bf4ps:weapon-catalog-persistence'))")
    )

    ownership = conn.execute(
        text(
            """
            SELECT 1
            FROM collection_jobs
            WHERE job_id = :job_id
              AND soldier_id = :soldier_id
              AND resource = 'weapons'
              AND status = 'running'
              AND collector_uuid = :collector_uuid
              AND lease_token = :lease_token
              AND lease_expires_at > now()
            FOR UPDATE
            """
        ),
        {
            "job_id": job.job_id,
            "soldier_id": job.soldier_id,
            "collector_uuid": job.collector_uuid,
            "lease_token": job.lease_token,
        },
    ).one_or_none()
    if ownership is None:
        raise RuntimeError("weapon success rejected: job lease is no longer owned")

    # Reconcile the global catalog first. The GUID is the durable Battlelog
    # identity; descriptive fields follow the latest successfully normalized
    # observation while first_seen_at remains immutable.
    weapon_ids: dict[str, int] = {}
    ordered_weapons = sorted(weapons, key=lambda item: item.weapon_guid)
    if ordered_weapons:
        catalog_rows = [
            {"weapon_guid": item.weapon_guid, "name": item.name, "slug": item.slug,
             "category": item.category} for item in ordered_weapons
        ]
        values_sql, params = bulk_values(catalog_rows, (('weapon_guid', 'name', 'slug', 'category')))
        params["source_fetched_at"] = source_fetched_at
        rows = conn.execute(text(
            "INSERT INTO weapon_catalog (weapon_guid, name, slug, category, first_seen_at, last_seen_at) "
            "VALUES " + values_sql.replace(")", ", :source_fetched_at, :source_fetched_at)") +
            " ON CONFLICT (weapon_guid) DO UPDATE SET "
            "name = EXCLUDED.name, slug = EXCLUDED.slug, "
            "category = EXCLUDED.category, last_seen_at = EXCLUDED.last_seen_at "
            "RETURNING weapon_guid, weapon_id"
        ), params)
        weapon_ids = {row[0]: int(row[1]) for row in rows}

    conn.execute(
        text("DELETE FROM soldier_weapon_stats WHERE soldier_id = :soldier_id"),
        {"soldier_id": job.soldier_id},
    )

    if weapons:
        stat_rows = [
            {"soldier_id": job.soldier_id, "weapon_id": weapon_ids[item.weapon_guid],
             "kills": item.kills, "headshots": item.headshots,
             "shots_fired": item.shots_fired, "shots_hit": item.shots_hit,
             "time_equipped_seconds": item.time_equipped_seconds,
             "source_fetched_at": source_fetched_at} for item in weapons
        ]
        values_sql, params = bulk_values(stat_rows, (('soldier_id', 'weapon_id', 'kills', 'headshots', 'shots_fired', 'shots_hit', 'time_equipped_seconds', 'source_fetched_at')))
        conn.execute(text(
            "INSERT INTO soldier_weapon_stats (soldier_id, weapon_id, kills, headshots, shots_fired, shots_hit, time_equipped_seconds, source_fetched_at, updated_at) VALUES "
            + values_sql.replace(")", ", now())")
        ), params)

    conn.execute(
        text(
            """
            INSERT INTO collection_state
                (soldier_id, weapons_state, weapons_last_attempt_at,
                 weapons_last_success_at, weapons_next_due_at,
                 weapons_consecutive_failures, weapons_last_error_class,
                 weapons_last_error_message, updated_at)
            VALUES
                (:soldier_id, 'success', :source_fetched_at,
                 :source_fetched_at, :source_fetched_at + interval '7 days', 0, NULL, NULL, now())
            ON CONFLICT (soldier_id) DO UPDATE
            SET weapons_state = 'success',
                weapons_last_attempt_at = EXCLUDED.weapons_last_attempt_at,
                weapons_last_success_at = EXCLUDED.weapons_last_success_at,
                weapons_next_due_at = EXCLUDED.weapons_next_due_at,
                weapons_consecutive_failures = 0,
                weapons_last_error_class = NULL,
                weapons_last_error_message = NULL,
                updated_at = now()
            """
        ),
        {"soldier_id": job.soldier_id, "source_fetched_at": source_fetched_at},
    )

    conn.execute(
        text(
            """
            INSERT INTO collection_events
                (collector_uuid, collector_name_snapshot, hostname_snapshot,
                 egress_key_snapshot, job_id, soldier_id, persona_id, platform,
                 resource, lane, event_type, attempt_number, result,
                 duration_ms, http_status, lease_token, metadata)
            VALUES
                (:collector_uuid, :collector_name, :hostname, :egress_key,
                 :job_id, :soldier_id, :persona_id, :platform,
                 'weapons', :lane, 'collection_success', :attempt_number,
                 'success', :duration_ms, :http_status, :lease_token,
                 jsonb_build_object('weapon_rows', :weapon_rows,
                                    'response_bytes', :response_bytes))
            """
        ),
        {
            "collector_uuid": job.collector_uuid,
            "collector_name": collector_name,
            "hostname": hostname,
            "egress_key": egress_key,
            "job_id": job.job_id,
            "soldier_id": job.soldier_id,
            "persona_id": persona_id,
            "platform": platform,
            "lane": job.lane,
            "attempt_number": job.attempt_count,
            "duration_ms": duration_ms,
            "http_status": http_status,
            "lease_token": job.lease_token,
            "weapon_rows": len(weapons),
            "response_bytes": response_bytes,
        },
    )

    finalized = conn.execute(
        text(
            """
            DELETE FROM collection_jobs
            WHERE job_id = :job_id
              AND collector_uuid = :collector_uuid
              AND lease_token = :lease_token
              AND status = 'running'
              AND lease_expires_at > now()
            """
        ),
        {
            "job_id": job.job_id,
            "collector_uuid": job.collector_uuid,
            "lease_token": job.lease_token,
        },
    )
    if finalized.rowcount != 1:
        raise RuntimeError("weapon success rejected during finalization: lease ownership lost")

    return len(weapons)