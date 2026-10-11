"""Offline three-site committed claim reconciliation tests."""
import copy
import pytest

from scripts.phase5b_three_site_claim_reconcile import reconcile_claim_reports
from scripts.phase5b_three_site_coordinator import FleetPlan
from scripts.phase5b_three_site_manifest import RunManifest


def sample():
    manifest = RunManifest.build(
        run_id="claims_oct10",
        distribution={"tcou": 1, "kah-01": 1, "hnl-01": 1},
        job_count=3)
    document = manifest.report()
    workers = FleetPlan.build(manifest.run_id, manifest.distribution).workers()
    reports = []
    db_claims = []
    for i, worker in enumerate(workers):
        claim = {
            "host": worker.host, "worker_index": worker.worker_index,
            "collector_uuid": str(worker.collector_uuid),
            "job_id": 200 + i, "soldier_id": 100 + i,
            "attempt_count": 1, "lease_token": f"synthetic-token-{i}",
        }
        report = worker.report()
        report.update(mode="synthetic-d2-claims", database_writes=1,
                      manifest_sha256=document["sha256"], claims=[claim])
        reports.append(report)
        db_claims.append({"job_id": claim["job_id"], "attempt_count": 1,
                          "collector_uuid": str(worker.collector_uuid)})
    state = {"run_id": manifest.run_id, "manifest_sha256": document["sha256"],
             "job_ids": [200, 201, 202]}
    committed = {"run_id": manifest.run_id, "jobs": 3, "claimed": 3,
                 "claims": db_claims}
    return document, state, reports, committed


def test_valid_three_host_claims():
    d, s, r, c = sample()
    result = reconcile_claim_reports(d, s, r, c)
    assert result["claimed"] == 3
    assert result["duplicate_committed_jobs"] == 0
    assert len(result["per_host"]) == 3


@pytest.mark.parametrize("mutation", [
    "missing_worker", "duplicate_worker", "wrong_manifest", "http",
    "wrong_collector", "duplicate_job", "wrong_attempt", "wrong_db_owner",
    "missing_db_claim", "wrong_run", "wrong_write_count",
])
def test_reject_invalid_reports(mutation):
    d, s, r, c = sample()
    d, s, r, c = copy.deepcopy((d, s, r, c))
    if mutation == "missing_worker":
        r.pop()
    elif mutation == "duplicate_worker":
        r[1] = r[0]
    elif mutation == "wrong_manifest":
        r[0]["manifest_sha256"] = "wrong"
    elif mutation == "http":
        r[0]["http_requests"] = 1
    elif mutation == "wrong_collector":
        r[0]["claims"][0]["collector_uuid"] = "other"
    elif mutation == "duplicate_job":
        r[1]["claims"][0]["job_id"] = r[0]["claims"][0]["job_id"]
    elif mutation == "wrong_attempt":
        r[0]["claims"][0]["attempt_count"] = 2
    elif mutation == "wrong_db_owner":
        c["claims"][0]["collector_uuid"] = "other"
    elif mutation == "missing_db_claim":
        c["claims"].pop()
        c["claimed"] = 2
    elif mutation == "wrong_run":
        s["run_id"] = "other"
    elif mutation == "wrong_write_count":
        r[0]["database_writes"] = 2
    with pytest.raises(ValueError):
        reconcile_claim_reports(d, s, r, c)
