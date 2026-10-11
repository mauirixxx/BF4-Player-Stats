"""Offline tests for bounded synthetic D2 soak worker (no DB, no HTTP)."""
from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest

from scripts.phase5b_three_site_manifest import RunManifest
from scripts.phase5b_three_site_soak_worker import run


def fixture():
    manifest = RunManifest.build(run_id="soak-test", distribution={
        "tcou": 1, "kah-01": 1, "hnl-01": 1,
    }, job_count=1, claim_limit_per_worker=1, lease_seconds=30)
    return manifest.report(), {
        "run_id": manifest.run_id, "manifest_sha256": manifest.report()["sha256"],
        "soldier_ids": [101], "job_ids": [201],
    }


@pytest.mark.parametrize("duration,interval,iterations", [
    (0, 1, 1), (14401, 1, 1), (1, 0, 1), (1, 3601, 1),
    (1, 1, 0), (1, 1, 100001),
])
def test_invalid_bounds_fail_before_database(duration, interval, iterations):
    doc, state = fixture()
    with pytest.raises(ValueError):
        run(manifest_document=doc, state=state, host="tcou", index=0,
            duration_seconds=duration, interval_seconds=interval,
            max_iterations=iterations, execute=True, url="unused")


def test_dry_run_no_database():
    doc, state = fixture()
    result = run(manifest_document=doc, state=state, host="tcou", index=0,
                 duration_seconds=30, interval_seconds=1,
                 max_iterations=5, execute=False, url=None)
    assert result["mode"] == "dry-run"
    assert result["claims"] == result["http_requests"] == 0


def test_tampered_state_rejected():
    doc, state = fixture()
    state["manifest_sha256"] = "wrong"
    with pytest.raises(ValueError):
        run(manifest_document=doc, state=state, host="tcou", index=0,
            duration_seconds=30, interval_seconds=1,
            max_iterations=5, execute=False, url=None)


def test_stop_before_first_claim():
    doc, state = fixture()
    with patch("scripts.phase5b_three_site_soak_worker.check_database_identity"), \
         patch("scripts.phase5b_three_site_soak_worker.create_engine") as engine, \
         patch("scripts.phase5b_three_site_soak_worker.validate_claim_cohort"):
        engine.return_value.connect.return_value.__enter__.return_value.rollback.return_value = None
        result = run(manifest_document=doc, state=state, host="tcou", index=0,
                     duration_seconds=30, interval_seconds=1,
                     max_iterations=5, execute=True, url="synthetic",
                     should_stop=lambda: True)
    assert result["status"] == "stopped"
    assert result["iterations"] == 0
    assert result["http_requests"] == 0


def test_bounded_one_claim_and_release():
    doc, state = fixture()
    job = type("Job", (), {"job_id": 201, "lease_token": uuid4()})()
    heartbeats = []
    with patch("scripts.phase5b_three_site_soak_worker.check_database_identity"), \
         patch("scripts.phase5b_three_site_soak_worker.create_engine") as engine, \
         patch("scripts.phase5b_three_site_soak_worker.validate_claim_cohort"), \
         patch("scripts.phase5b_three_site_soak_worker.claim_next_job", return_value=job), \
         patch("scripts.phase5b_three_site_soak_worker.mark_job_running", return_value=True), \
         patch("scripts.phase5b_three_site_soak_worker.release_for_retry", return_value=True):
        result = run(manifest_document=doc, state=state, host="tcou", index=0,
                     duration_seconds=30, interval_seconds=1,
                     max_iterations=1, execute=True, url="synthetic",
                     sleep=lambda _: None, heartbeat=heartbeats.append)
    assert result["status"] == "complete"
    assert (result["iterations"], result["claims"], result["releases"]) == (1, 1, 1)
    assert len(heartbeats) == 1
    assert result["http_requests"] == 0
