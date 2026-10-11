"""Offline contract tests for guarded three-site D2 claim worker."""
from unittest.mock import patch
import pytest

from scripts.phase5b_three_site_claim_worker import run, validate_claim_cohort
from scripts.phase5b_three_site_manifest import RunManifest


@pytest.fixture
def document():
    return RunManifest.build(
        run_id="oct10", distribution={"tcou": 3, "kah-01": 3, "hnl-01": 2}
    ).report()


@pytest.mark.parametrize("host,index", [
    ("tcou", 0), ("tcou", 2), ("kah-01", 1), ("hnl-01", 1)
])
def test_dry_run_does_not_open_database(document, host, index):
    with patch("scripts.phase5b_three_site_claim_worker.create_engine",
               side_effect=AssertionError("database must remain untouched")):
        result = run(manifest_document=document, host=host, index=index,
                     soldier_ids=[], execute=False, url=None)
    assert result["mode"] == "dry-run"
    assert result["http_requests"] == result["database_writes"] == 0
    assert result["manifest_sha256"] == document["sha256"]


@pytest.mark.parametrize("host,index", [
    ("other", 0), ("tcou", -1), ("tcou", 3), ("hnl-01", 2)
])
def test_invalid_worker_fails_closed(document, host, index):
    with pytest.raises(ValueError):
        run(manifest_document=document, host=host, index=index,
            soldier_ids=[], execute=False, url=None)


def test_execute_requires_credentials(document):
    with pytest.raises(ValueError, match="BF4PS_STAGE9C_D2_URL"):
        run(manifest_document=document, host="tcou", index=0,
            soldier_ids=[1], execute=True, url=None)


@pytest.mark.parametrize("ids", [[], [1, 1], [0], [-2], list(range(1, 10002))])
def test_reject_bad_cohort_before_sql(ids):
    with pytest.raises(ValueError):
        validate_claim_cohort(None, run_id="oct10", soldier_ids=ids,
                              collector_uuid="unused", host="tcou")


def test_tampered_manifest_rejected(document):
    document["manifest"]["http_enabled"] = True
    with pytest.raises(ValueError):
        run(manifest_document=document, host="tcou", index=0,
            soldier_ids=[], execute=False, url=None)
