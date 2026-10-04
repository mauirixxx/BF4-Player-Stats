from decimal import Decimal

import pytest

from bf4ps.battlelog_detailed import (
    DetailedStatsNormalizationError,
    UnsupportedPlatformError,
    detailed_stats_url,
    normalize_detailed_stats,
    platform_int,
)


def test_platform_mapping_matches_battlelog_contract():
    assert platform_int("pc") == 1
    assert platform_int("ps4") == 32
    assert platform_int("xboxone") == 64


def test_unknown_platform_is_rejected():
    with pytest.raises(UnsupportedPlatformError):
        platform_int("ps3")


def test_detailed_url_uses_persona_and_platform_int():
    assert detailed_stats_url(236753552, "pc").endswith(
        "/bf4/warsawdetailedstatspopulate/236753552/1/"
    )


def test_normalizer_maps_retained_fields_and_accepts_numeric_strings():
    payload = {
        "personaId": "236753552",
        "platformInt": 1,
        "generalStats": {
            "rank": "140",
            "timePlayed": 123456,
            "assault": "1000",
            "kills": "42",
            "deaths": 21,
            "quitPercentage": "0.125000",
            "longestHeadshot": "321.4567",
            "killStreakBonus": "17",
        },
    }

    result = normalize_detailed_stats(
        payload,
        expected_persona_id=236753552,
        expected_platform_int=1,
    )

    assert result["rank"] == 140
    assert result["time_played_seconds"] == 123456
    assert result["assault_score"] == 1000
    assert result["kills"] == 42
    assert result["deaths"] == 21
    assert result["quit_percentage"] == Decimal("0.125000")
    assert result["longest_headshot"] == Decimal("321.4567")
    assert result["highest_kill_streak"] == 17
    assert result["engineer_score"] is None


def test_normalizer_rejects_fractional_integer_counter():
    payload = {"generalStats": {"kills": "1.5"}}
    with pytest.raises(DetailedStatsNormalizationError, match="kills: expected integer"):
        normalize_detailed_stats(payload)


def test_normalizer_rejects_boolean_counter():
    payload = {"generalStats": {"kills": True}}
    with pytest.raises(DetailedStatsNormalizationError, match="boolean is not numeric"):
        normalize_detailed_stats(payload)


def test_normalizer_rejects_missing_general_stats():
    with pytest.raises(DetailedStatsNormalizationError, match="generalStats"):
        normalize_detailed_stats({})


def test_normalizer_fences_wrong_persona_payload():
    payload = {"personaId": 999, "generalStats": {}}
    with pytest.raises(DetailedStatsNormalizationError, match="personaId mismatch"):
        normalize_detailed_stats(payload, expected_persona_id=236753552)


def test_normalizer_fences_wrong_platform_payload():
    payload = {"platformInt": 64, "generalStats": {}}
    with pytest.raises(DetailedStatsNormalizationError, match="platformInt mismatch"):
        normalize_detailed_stats(payload, expected_platform_int=1)
