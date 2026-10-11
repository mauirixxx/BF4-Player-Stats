"""Offline safety checks for the D2 coordinator state envelope."""
import pytest
from scripts.phase5b_three_site_d2_coordinator import cohort_prefix, validate_state
from scripts.phase5b_three_site_manifest import RunManifest


def fixture_state():
    manifest = RunManifest.build(run_id="test_cohort",
        distribution={"tcou": 1, "kah-01": 1, "hnl-01": 1},
        job_count=2)
    state = {"run_id": manifest.run_id,
             "manifest_sha256": manifest.report()["sha256"],
             "soldier_ids": [101, 102], "job_ids": [201, 202]}
    return manifest, state


def test_synthetic_prefix_and_valid_state():
    manifest, state = fixture_state()
    assert cohort_prefix(manifest.run_id) == "synthetic-three-site-test_cohort-"
    validate_state(manifest, state)


@pytest.mark.parametrize("field,value", [
    ("run_id", "wrong"), ("manifest_sha256", "bad"),
    ("soldier_ids", [101, 101]), ("soldier_ids", [101]),
    ("soldier_ids", [0, 102]), ("job_ids", [201, 201]),
    ("job_ids", [201]), ("job_ids", [-1, 202]),
])
def test_mismatched_state_rejected(field, value):
    manifest, state = fixture_state()
    state[field] = value
    with pytest.raises(ValueError):
        validate_state(manifest, state)
