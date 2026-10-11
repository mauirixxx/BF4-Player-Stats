"""Offline tests for distributed D2 run manifests."""
import copy
import pytest
from scripts.phase5b_three_site_manifest import RunManifest, validate_manifest_document


@pytest.mark.parametrize("distribution,total", [
    ({"tcou": 1, "kah-01": 1, "hnl-01": 1}, 3),
    ({"tcou": 3, "kah-01": 3, "hnl-01": 2}, 8),
    ({"tcou": 6, "kah-01": 5, "hnl-01": 5}, 16),
    ({"tcou": 12, "kah-01": 10, "hnl-01": 10}, 32),
])
def test_manifest_round_trip(distribution, total):
    manifest = RunManifest.build(run_id="three_site_oct10", distribution=distribution)
    document = manifest.report()
    assert document["manifest"]["worker_count"] == total
    assert len(set(document["manifest"]["collector_uuids"])) == total
    assert validate_manifest_document(document) == manifest
    assert document["sha256"] == manifest.report()["sha256"]


@pytest.mark.parametrize("field,value", [
    ("job_count", 0), ("job_count", 10001),
    ("claim_limit_per_worker", 0), ("lease_seconds", 29),
    ("lease_seconds", 3601), ("http_enabled", True),
    ("production_enabled", True), ("synthetic_only", False),
    ("worker_count", 99), ("collector_uuids", []),
    ("schema", "unknown"),
])
def test_rejects_tampered_manifest(field, value):
    document = RunManifest.build(
        run_id="three_site_oct10",
        distribution={"tcou": 3, "kah-01": 3, "hnl-01": 2}
    ).report()
    tampered = copy.deepcopy(document)
    tampered["manifest"][field] = value
    with pytest.raises(ValueError):
        validate_manifest_document(tampered)


def test_rejects_digest_tampering():
    document = RunManifest.build(
        run_id="test", distribution={"tcou": 1}).report()
    document["sha256"] = "0" * 64
    with pytest.raises(ValueError):
        validate_manifest_document(document)
