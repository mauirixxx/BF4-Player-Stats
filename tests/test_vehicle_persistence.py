from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from bf4ps.battlelog_vehicles import NormalizedVehicleStat
from bf4ps.vehicle_persistence import _validate_vehicles, persist_vehicle_success


def vehicle(guid: str = "GUID-A", destroy: Decimal | None = Decimal("2")) -> NormalizedVehicleStat:
    return NormalizedVehicleStat(
        vehicle_guid=guid,
        name="WARSAW_ID_P_XP1_VNAME_BTR90",
        slug="btr-90",
        category="Vehicle Infantry Fighting Vehicle",
        kills=12,
        time_in_seconds=1574,
        destroy_x_in_y=destroy,
    )


def job(resource: str = "vehicles") -> SimpleNamespace:
    return SimpleNamespace(
        job_id=10,
        soldier_id=20,
        resource=resource,
        collector_uuid="00000000-0000-0000-0000-000000000001",
        lease_token="00000000-0000-0000-0000-000000000002",
        lane="background",
        attempt_count=1,
    )


def test_validate_vehicles_accepts_unique_guids_and_integral_destroy_value():
    _validate_vehicles([vehicle("A"), vehicle("B", None), vehicle("C", Decimal("0.0"))])


def test_validate_vehicles_rejects_duplicate_guids():
    with pytest.raises(ValueError, match="duplicate vehicle_guid"):
        _validate_vehicles([vehicle("A"), replace(vehicle("B"), vehicle_guid="A")])


def test_validate_vehicles_rejects_fractional_destroy_value_before_sql():
    with pytest.raises(ValueError, match="cannot be persisted losslessly"):
        _validate_vehicles([vehicle(destroy=Decimal("1.5"))])


def test_persistence_rejects_wrong_resource_before_sql():
    with pytest.raises(ValueError, match="requires a vehicles job"):
        persist_vehicle_success(
            None, job=job("weapons"), vehicles=[],
            source_fetched_at=datetime.now(timezone.utc), persona_id=1,
            platform="pc", collector_name="collector", hostname="host",
            egress_key="egress", duration_ms=1, response_bytes=1,
        )


def test_persistence_rejects_negative_duration_before_sql():
    with pytest.raises(ValueError, match="duration_ms"):
        persist_vehicle_success(
            None, job=job(), vehicles=[],
            source_fetched_at=datetime.now(timezone.utc), persona_id=1,
            platform="pc", collector_name="collector", hostname="host",
            egress_key="egress", duration_ms=-1, response_bytes=1,
        )


def test_persistence_rejects_negative_response_bytes_before_sql():
    with pytest.raises(ValueError, match="response_bytes"):
        persist_vehicle_success(
            None, job=job(), vehicles=[],
            source_fetched_at=datetime.now(timezone.utc), persona_id=1,
            platform="pc", collector_name="collector", hostname="host",
            egress_key="egress", duration_ms=1, response_bytes=-1,
        )


def test_vehicle_persistence_serializes_shared_catalog_and_orders_guids():
    source = Path("bf4ps/vehicle_persistence.py").read_text(encoding="utf-8")
    assert "pg_advisory_xact_lock" in source
    assert "bf4ps:vehicle-catalog-persistence" in source
    assert "sorted(vehicles, key=lambda item: item.vehicle_guid)" in source
    lock_pos = source.index("pg_advisory_xact_lock")
    ownership_pos = source.index("SELECT 1")
    catalog_pos = source.index("INSERT INTO vehicle_catalog")
    assert lock_pos < ownership_pos < catalog_pos


def test_vehicle_persistence_uses_documented_vehicle_state_family():
    source = Path("bf4ps/vehicle_persistence.py").read_text(encoding="utf-8")
    assert "vehicles_state" in source
    assert "vehicles_last_attempt_at" in source
    assert "vehicles_last_success_at" in source
    assert "vehicles_consecutive_failures" in source
    assert "resource = 'vehicles'" in source
