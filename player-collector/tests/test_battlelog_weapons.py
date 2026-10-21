from __future__ import annotations

import pytest

from bf4ps.battlelog_weapons import (
    WeaponStatsNormalizationError,
    normalize_weapon_stats,
    weapon_stats_url,
)


def _payload() -> dict:
    return {
        "type": "success",
        "message": "OK",
        "data": {
            "personaId": 236753552,
            "platformInt": 1,
            "mainWeaponStats": [
                {
                    "guid": "AEK-GUID",
                    "slug": "aek-971",
                    "name": "AEK-971",
                    "category": "Assault Rifles",
                    "kills": 3436,
                    "deaths": 100,
                    "headshots": 666,
                    "shotsFired": 161837,
                    "shotsHit": 20034,
                    "accuracy": 12.379,
                    "score": 999999,
                    "timeEquipped": 152934,
                    "serviceStars": 34,
                    "serviceStarsProgress": 0.36,
                }
            ],
        },
    }


def test_weapon_stats_url_uses_platform_mapping() -> None:
    assert weapon_stats_url(236753552, "pc").endswith(
        "/bf4/warsawWeaponsPopulateStats/236753552/1/stats/"
    )
    assert weapon_stats_url(123, "ps4").endswith(
        "/bf4/warsawWeaponsPopulateStats/123/32/stats/"
    )
    assert weapon_stats_url(456, "xboxone").endswith(
        "/bf4/warsawWeaponsPopulateStats/456/64/stats/"
    )


def test_normalizer_retains_only_frozen_weapon_contract() -> None:
    result = normalize_weapon_stats(
        _payload(), expected_persona_id=236753552, expected_platform_int=1
    )
    assert len(result) == 1
    weapon = result[0]
    assert weapon.weapon_guid == "AEK-GUID"
    assert weapon.name == "AEK-971"
    assert weapon.slug == "aek-971"
    assert weapon.category == "Assault Rifles"
    assert weapon.kills == 3436
    assert weapon.headshots == 666
    assert weapon.shots_fired == 161837
    assert weapon.shots_hit == 20034
    assert weapon.time_equipped_seconds == 152934
    assert not hasattr(weapon, "deaths")
    assert not hasattr(weapon, "accuracy")
    assert not hasattr(weapon, "score")
    assert not hasattr(weapon, "service_stars")


def test_normalizer_accepts_inner_data_fixture() -> None:
    inner = _payload()["data"]
    result = normalize_weapon_stats(inner)
    assert result[0].weapon_guid == "AEK-GUID"


def test_normalizer_accepts_explicit_null_non_applicable_melee_counters() -> None:
    payload = _payload()
    payload["data"]["mainWeaponStats"][0] = {
        "guid": "DB4E0973-32D1-4A9A-B598-EA0743E76B67",
        "slug": "knife-bowie",
        "name": "WARSAW_ID_P_INAME_BPKNIFE6",
        "category": "Special",
        "kills": 2078,
        "headshots": None,
        "shotsFired": None,
        "shotsHit": None,
        "timeEquipped": None,
    }

    result = normalize_weapon_stats(payload)
    assert len(result) == 1
    weapon = result[0]
    assert weapon.kills == 2078
    assert weapon.headshots == 0
    assert weapon.shots_fired == 0
    assert weapon.shots_hit == 0
    assert weapon.time_equipped_seconds == 0


def test_normalizer_rejects_missing_weapon_collection() -> None:
    payload = _payload()
    del payload["data"]["mainWeaponStats"]
    with pytest.raises(WeaponStatsNormalizationError, match="mainWeaponStats"):
        normalize_weapon_stats(payload)


def test_normalizer_rejects_malformed_entry() -> None:
    payload = _payload()
    payload["data"]["mainWeaponStats"] = ["not-an-object"]
    with pytest.raises(WeaponStatsNormalizationError, match="not an object"):
        normalize_weapon_stats(payload)


def test_normalizer_rejects_missing_required_retained_counter() -> None:
    payload = _payload()
    del payload["data"]["mainWeaponStats"][0]["shotsHit"]
    with pytest.raises(WeaponStatsNormalizationError, match="shotsHit"):
        normalize_weapon_stats(payload)


def test_normalizer_rejects_fractional_counter() -> None:
    payload = _payload()
    payload["data"]["mainWeaponStats"][0]["kills"] = 1.5
    with pytest.raises(WeaponStatsNormalizationError, match="expected integer"):
        normalize_weapon_stats(payload)


def test_normalizer_rejects_negative_counter() -> None:
    payload = _payload()
    payload["data"]["mainWeaponStats"][0]["headshots"] = -1
    with pytest.raises(WeaponStatsNormalizationError, match="non-negative"):
        normalize_weapon_stats(payload)


def test_normalizer_rejects_duplicate_guid() -> None:
    payload = _payload()
    payload["data"]["mainWeaponStats"].append(
        dict(payload["data"]["mainWeaponStats"][0])
    )
    with pytest.raises(WeaponStatsNormalizationError, match="duplicate weapon guid"):
        normalize_weapon_stats(payload)


def test_normalizer_rejects_persona_mismatch() -> None:
    with pytest.raises(WeaponStatsNormalizationError, match="personaId mismatch"):
        normalize_weapon_stats(_payload(), expected_persona_id=1)


def test_normalizer_rejects_platform_mismatch() -> None:
    with pytest.raises(WeaponStatsNormalizationError, match="platformInt mismatch"):
        normalize_weapon_stats(_payload(), expected_platform_int=64)
