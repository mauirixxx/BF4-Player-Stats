"""Offline validation tests for the bounded Stage 9C batch manifest."""
import pytest

from scripts.stage9c_batch_preflight import parse_manifest


def good():
    return {"version": 1,
            "soldiers": [{"platform": "pc", "persona_id": 236753552},
                         {"platform": "ps4", "persona_id": 303498475}],
            "resources": ["detailed", "weapons"], "max_attempts": 4}


def test_valid_manifest():
    soldiers, resources, limit = parse_manifest(good())
    assert soldiers == (("pc", 236753552), ("ps4", 303498475))
    assert resources == ("detailed", "weapons")
    assert limit == 4


@pytest.mark.parametrize("field,value", [
    ("version", 2), ("soldiers", []), ("resources", ["profile"]),
    ("resources", ["weapons", "weapons"]), ("max_attempts", 0),
    ("max_attempts", 5), ("max_attempts", True),
])
def test_invalid_top_level(field, value):
    manifest = good()
    manifest[field] = value
    with pytest.raises(ValueError):
        parse_manifest(manifest)


def test_duplicate_identity():
    manifest = good()
    manifest["soldiers"].append(manifest["soldiers"][0].copy())
    with pytest.raises(ValueError, match="duplicate"):
        parse_manifest(manifest)


@pytest.mark.parametrize("platform,persona", [
    ("ps3", 123), ("pc", 0), ("pc", -5), ("pc", "123"), ("pc", True)
])
def test_invalid_identity(platform, persona):
    manifest = good()
    manifest["soldiers"][0] = {"platform": platform, "persona_id": persona}
    with pytest.raises(ValueError):
        parse_manifest(manifest)
