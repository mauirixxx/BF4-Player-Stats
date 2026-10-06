from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
from pathlib import Path

import pytest

from bf4ps.battlelog_weapons import NormalizedWeaponStat
from bf4ps.weapon_persistence import _validate_weapons, persist_weapon_success


def weapon(guid: str = "GUID-A") -> NormalizedWeaponStat:
    return NormalizedWeaponStat(
        weapon_guid=guid,
        name="AEK-971",
        slug="aek-971",
        category="Assault Rifles",
        kills=10,
        headshots=2,
        shots_fired=100,
        shots_hit=25,
        time_equipped_seconds=60,
    )


def job(resource: str = "weapons") -> SimpleNamespace:
    return SimpleNamespace(
        job_id=10,
        soldier_id=20,
        resource=resource,
        collector_uuid="00000000-0000-0000-0000-000000000001",
        lease_token="00000000-0000-0000-0000-000000000002",
        lane="background",
        attempt_count=1,
    )


def test_validate_weapons_accepts_unique_guids() -> None:
    _validate_weapons([weapon("A"), weapon("B")])


def test_validate_weapons_rejects_duplicate_guids() -> None:
    with pytest.raises(ValueError, match="duplicate weapon_guid"):
        _validate_weapons([weapon("A"), replace(weapon("B"), weapon_guid="A")])


def test_persistence_rejects_wrong_resource_before_sql() -> None:
    with pytest.raises(ValueError, match="requires a weapons job"):
        persist_weapon_success(
            None,  # type: ignore[arg-type]
            job=job("detailed"),
            weapons=[],
            source_fetched_at=datetime.now(timezone.utc),
            persona_id=1,
            platform="pc",
            collector_name="collector",
            hostname="host",
            egress_key="egress",
            duration_ms=1,
            response_bytes=1,
        )


def test_persistence_rejects_negative_duration_before_sql() -> None:
    with pytest.raises(ValueError, match="duration_ms"):
        persist_weapon_success(
            None,  # type: ignore[arg-type]
            job=job(),
            weapons=[],
            source_fetched_at=datetime.now(timezone.utc),
            persona_id=1,
            platform="pc",
            collector_name="collector",
            hostname="host",
            egress_key="egress",
            duration_ms=-1,
            response_bytes=1,
        )


def test_persistence_rejects_negative_response_bytes_before_sql() -> None:
    with pytest.raises(ValueError, match="response_bytes"):
        persist_weapon_success(
            None,  # type: ignore[arg-type]
            job=job(),
            weapons=[],
            source_fetched_at=datetime.now(timezone.utc),
            persona_id=1,
            platform="pc",
            collector_name="collector",
            hostname="host",
            egress_key="egress",
            duration_ms=1,
            response_bytes=-1,
        )


def test_persistence_rejects_invalid_http_status_before_sql() -> None:
    with pytest.raises(ValueError, match="http_status"):
        persist_weapon_success(
            None,  # type: ignore[arg-type]
            job=job(),
            weapons=[],
            source_fetched_at=datetime.now(timezone.utc),
            persona_id=1,
            platform="pc",
            collector_name="collector",
            hostname="host",
            egress_key="egress",
            duration_ms=1,
            response_bytes=1,
            http_status=99,
        )


def test_weapon_persistence_serializes_shared_catalog_and_orders_guids() -> None:
    source = Path("bf4ps/weapon_persistence.py").read_text(encoding="utf-8")
    assert "pg_advisory_xact_lock" in source
    assert "bf4ps:weapon-catalog-persistence" in source
    assert "sorted(weapons, key=lambda item: item.weapon_guid)" in source
