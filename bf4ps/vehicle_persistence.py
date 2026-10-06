"""Atomic persistence for successful BF4 vehicle-statistics collection."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Sequence

from sqlalchemy import text
from sqlalchemy.engine import Connection

from bf4ps.battlelog_vehicles import NormalizedVehicleStat
from bf4ps.collection_jobs import ClaimedJob


def _validate_vehicles(vehicles: Sequence[NormalizedVehicleStat]) -> None:
    seen: set[str] = set()
    for vehicle in vehicles:
        if vehicle.vehicle_guid in seen:
            raise ValueError(f"duplicate vehicle_guid: {vehicle.vehicle_guid!r}")
        seen.add(vehicle.vehicle_guid)
        value = vehicle.destroy_x_in_y
        if value is not None:
            decimal_value = Decimal(value)
            if decimal_value != decimal_value.to_integral_value():
                raise ValueError(
                    "destroy_x_in_y cannot be persisted losslessly to the "
                    f"documented BIGINT column: {value!r}"
                )


def persist_vehicle_success(
    conn: Connection,
    *,
    job: ClaimedJob,
    vehicles: Sequence[NormalizedVehicleStat],
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
    """Persist one successful vehicle fetch and finalize its owned queue job."""
    if job.resource != "vehicles":
        raise ValueError("persist_vehicle_success requires a vehicles job")
    if duration_ms < 0:
        raise ValueError("duration_ms must be non-negative")
    if response_bytes < 0:
        raise ValueError("response_bytes must be non-negative")
    if not 100 <= http_status <= 599:
        raise ValueError("http_status must be between 100 and 599")
    _validate_vehicles(vehicles)

    # All collectors reconcile the same global catalog. Preserve the Stage A
    # concurrency lesson from the first vehicle write: serialize this critical
    # section and acquire catalog identities in deterministic GUID order.
    conn.execute(
        text("SELECT pg_advisory_xact_lock(hashtext('bf4ps:vehicle-catalog-persistence'))")
    )

    ownership = conn.execute(
        text(
            """
            SELECT 1
            FROM collection_jobs
            WHERE job_id = :job_id
              AND soldier_id = :soldier_id
              AND resource = 'vehicles'
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
        raise RuntimeError("vehicle success rejected: job lease is no longer owned")

    vehicle_ids: dict[str, int] = {}
    ordered_vehicles = sorted(vehicles, key=lambda item: item.vehicle_guid)
    for vehicle in ordered_vehicles:
        row = conn.execute(
            text(
                """
                INSERT INTO vehicle_catalog
                    (vehicle_guid, name, slug, category, first_seen_at, last_seen_at)
                VALUES
                    (:vehicle_guid, :name, :slug, :category,
                     :source_fetched_at, :source_fetched_at)
                ON CONFLICT (vehicle_guid) DO UPDATE
                SET name = EXCLUDED.name,
                    slug = EXCLUDED.slug,
                    category = EXCLUDED.category,
                    last_seen_at = EXCLUDED.last_seen_at
                RETURNING vehicle_id
                """
            ),
            {
                "vehicle_guid": vehicle.vehicle_guid,
                "name": vehicle.name,
                "slug": vehicle.slug,
                "category": vehicle.category,
                "source_fetched_at": source_fetched_at,
            },
        ).one()
        vehicle_ids[vehicle.vehicle_guid] = int(row[0])

    conn.execute(
        text("DELETE FROM soldier_vehicle_stats WHERE soldier_id = :soldier_id"),
        {"soldier_id": job.soldier_id},
    )

    for vehicle in vehicles:
        destroy_x_in_y = (
            None if vehicle.destroy_x_in_y is None else int(vehicle.destroy_x_in_y)
        )
        conn.execute(
            text(
                """
                INSERT INTO soldier_vehicle_stats
                    (soldier_id, vehicle_id, kills, time_in_seconds,
                     destroy_x_in_y, source_fetched_at, updated_at)
                VALUES
                    (:soldier_id, :vehicle_id, :kills, :time_in_seconds,
                     :destroy_x_in_y, :source_fetched_at, now())
                """
            ),
            {
                "soldier_id": job.soldier_id,
                "vehicle_id": vehicle_ids[vehicle.vehicle_guid],
                "kills": vehicle.kills,
                "time_in_seconds": vehicle.time_in_seconds,
                "destroy_x_in_y": destroy_x_in_y,
                "source_fetched_at": source_fetched_at,
            },
        )

    conn.execute(
        text(
            """
            INSERT INTO collection_state
                (soldier_id, vehicles_state, vehicles_last_attempt_at,
                 vehicles_last_success_at, vehicles_next_due_at,
                 vehicles_consecutive_failures, vehicles_last_error_class,
                 vehicles_last_error_message, updated_at)
            VALUES
                (:soldier_id, 'success', :source_fetched_at,
                 :source_fetched_at, :source_fetched_at + interval '7 days', 0, NULL, NULL, now())
            ON CONFLICT (soldier_id) DO UPDATE
            SET vehicles_state = 'success',
                vehicles_last_attempt_at = EXCLUDED.vehicles_last_attempt_at,
                vehicles_last_success_at = EXCLUDED.vehicles_last_success_at,
                vehicles_next_due_at = EXCLUDED.vehicles_next_due_at,
                vehicles_consecutive_failures = 0,
                vehicles_last_error_class = NULL,
                vehicles_last_error_message = NULL,
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
                 'vehicles', :lane, 'collection_success', :attempt_number,
                 'success', :duration_ms, :http_status, :lease_token,
                 jsonb_build_object('vehicle_rows', :vehicle_rows,
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
            "vehicle_rows": len(vehicles),
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
        raise RuntimeError("vehicle success rejected during finalization: lease ownership lost")

    return len(vehicles)
