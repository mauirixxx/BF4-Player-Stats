from decimal import Decimal

import pytest

from bf4ps.battlelog_vehicles import (
    VehicleStatsNormalizationError,
    normalize_vehicle_stats,
    vehicle_stats_url,
)


def payload(entry=None):
    return {
        "data": {
            "personaId": 513446234,
            "platformInt": 1,
            "mainVehicleStats": [
                entry or {
                    "guid": "F998F5E4-220D-463A-A437-1C18D5C3A19E",
                    "name": "WARSAW_ID_P_XP1_VNAME_BTR90",
                    "slug": "btr-90",
                    "category": "Vehicle Infantry Fighting Vehicle",
                    "kills": 12,
                    "timeIn": 1574,
                    "destroyXinY": 0.0,
                }
            ],
        }
    }


def test_vehicle_url_uses_confirmed_endpoint_and_platform_mapping():
    assert vehicle_stats_url(513446234, "pc").endswith(
        "/bf4/warsawvehiclesPopulateStats/513446234/1/stats/"
    )


def test_normalizes_confirmed_live_vehicle_shape():
    rows = normalize_vehicle_stats(
        payload(), expected_persona_id=513446234, expected_platform_int=1
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.vehicle_guid == "F998F5E4-220D-463A-A437-1C18D5C3A19E"
    assert row.kills == 12
    assert row.time_in_seconds == 1574
    assert row.destroy_x_in_y == Decimal("0.0")


def test_destroy_x_in_y_may_be_explicit_null():
    p = payload()
    p["data"]["mainVehicleStats"][0]["destroyXinY"] = None
    assert normalize_vehicle_stats(p)[0].destroy_x_in_y is None


@pytest.mark.parametrize("key", ["guid", "name", "kills", "timeIn"])
def test_required_retained_fields_cannot_be_missing(key):
    p = payload()
    del p["data"]["mainVehicleStats"][0][key]
    with pytest.raises(VehicleStatsNormalizationError):
        normalize_vehicle_stats(p)


def test_requires_confirmed_main_vehicle_stats_container():
    with pytest.raises(VehicleStatsNormalizationError):
        normalize_vehicle_stats({"data": {"vehicles": []}})


def test_rejects_duplicate_vehicle_guid():
    p = payload()
    p["data"]["mainVehicleStats"].append(
        dict(p["data"]["mainVehicleStats"][0])
    )
    with pytest.raises(VehicleStatsNormalizationError):
        normalize_vehicle_stats(p)


def test_rejects_identity_mismatch():
    with pytest.raises(VehicleStatsNormalizationError):
        normalize_vehicle_stats(payload(), expected_persona_id=999, expected_platform_int=1)
