from decimal import Decimal

import pytest

from bf4ps.detailed_persistence import _canonicalize_stats


def test_canonicalize_stats_matches_postgresql_numeric_scales():
    stats = {
        "quit_percentage": Decimal("19.155806712028607"),
        "longest_headshot": Decimal("1734.94000000001"),
    }

    # _canonicalize_stats expects the complete retained contract. Populate the
    # remaining fields with harmless exact values for this boundary test.
    from bf4ps.detailed_persistence import DETAILED_FIELDS

    complete = {field: 0 for field in DETAILED_FIELDS}
    complete.update(stats)

    canonical = _canonicalize_stats(complete)

    assert canonical["quit_percentage"] == Decimal("19.155807")
    assert canonical["longest_headshot"] == Decimal("1734.9400")


def test_canonicalize_stats_does_not_mutate_input():
    from bf4ps.detailed_persistence import DETAILED_FIELDS

    complete = {field: 0 for field in DETAILED_FIELDS}
    complete["quit_percentage"] = Decimal("19.155806712028607")
    complete["longest_headshot"] = Decimal("1734.94")

    original_quit = complete["quit_percentage"]
    canonical = _canonicalize_stats(complete)

    assert complete["quit_percentage"] == original_quit
    assert canonical is not complete


def test_canonicalize_stats_rejects_non_decimal_decimal_field():
    from bf4ps.detailed_persistence import DETAILED_FIELDS

    complete = {field: 0 for field in DETAILED_FIELDS}
    complete["quit_percentage"] = 19.1
    complete["longest_headshot"] = Decimal("1734.94")

    with pytest.raises(TypeError, match="quit_percentage must be Decimal or None"):
        _canonicalize_stats(complete)
