"""Offline safety checks for the D2 coordinator state envelope."""
import pytest
from scripts.phase5b_three_site_d2_coordinator import cohort_prefix, validate_state, cleanup
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


class CleanupResult:
    def __init__(self, count):
        self.count = count

    def scalar_one(self):
        return self.count


class CleanupConnection:
    def __init__(self, active=0):
        self.active = active
        self.calls = []

    def execute(self, statement, parameters=None):
        sql = str(statement)
        self.calls.append((sql, parameters))
        if "status IN ('claimed','running')" in sql:
            return CleanupResult(self.active)
        if sql.startswith("SELECT count(*)"):
            return CleanupResult(0)
        return CleanupResult(0)


def test_cleanup_refuses_active_claims_before_deletion(monkeypatch):
    manifest, state = fixture_state()
    monkeypatch.setattr(
        "scripts.phase5b_three_site_d2_coordinator.verify",
        lambda conn, manifest, state: {"jobs": 2},
    )
    conn = CleanupConnection(active=1)
    with pytest.raises(RuntimeError, match="claimed or running"):
        cleanup(conn, manifest, state)
    assert not any("DELETE FROM" in sql for sql, _ in conn.calls)


def test_cleanup_uses_literal_prefix_not_sql_wildcards(monkeypatch):
    manifest, state = fixture_state()
    monkeypatch.setattr(
        "scripts.phase5b_three_site_d2_coordinator.verify",
        lambda conn, manifest, state: {"jobs": 2},
    )
    conn = CleanupConnection()
    cleanup(conn, manifest, state)
    deletions = [(sql, params) for sql, params in conn.calls if "DELETE FROM" in sql]
    assert len(deletions) == 5
    named = [(sql, params) for sql, params in deletions if ":prefix" in sql]
    assert len(named) == 2
    for sql, params in named:
        assert "LIKE" not in sql
        assert "left(" in sql
        assert params["prefix"] == cohort_prefix(manifest.run_id)
