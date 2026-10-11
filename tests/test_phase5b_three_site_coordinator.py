"""Coordinator offline planning and claim-result contract."""
import pytest
from scripts.phase5b_three_site_coordinator import FleetPlan, validate_claim_results


@pytest.mark.parametrize("distribution,total", [
    ({"tcou": 1, "kah-01": 1, "hnl-01": 1}, 3),
    ({"tcou": 3, "kah-01": 3, "hnl-01": 2}, 8),
    ({"tcou": 6, "kah-01": 5, "hnl-01": 5}, 16),
    ({"tcou": 12, "kah-01": 10, "hnl-01": 10}, 32),
    ({"tcou": 3, "kah-01": 0, "hnl-01": 0}, 3),
])
def test_fleet_plans(distribution, total):
    plan = FleetPlan.build("integration_20261010", distribution)
    report = plan.report()
    assert report["worker_count"] == total
    assert report["unique_collector_count"] == total
    assert report["database_writes"] == report["http_requests"] == 0


@pytest.mark.parametrize("distribution", [
    {}, {"untrusted": 1}, {"tcou": 0},
    {"tcou": -1}, {"tcou": 33}, {"tcou": True},
])
def test_bad_distributions_fail_closed(distribution):
    with pytest.raises(ValueError):
        FleetPlan.build("integration", distribution)


def test_claim_result_validation_and_duplicate_detection():
    claims = [
        {"host": "tcou", "job_id": 101, "attempt_count": 1},
        {"host": "kah-01", "job_id": 102, "attempt_count": 1},
        {"host": "hnl-01", "job_id": 101, "attempt_count": 2},
    ]
    report = validate_claim_results({101, 102}, claims)
    assert report["claims"] == 3
    assert report["per_host"] == {"hnl-01": 1, "kah-01": 1, "tcou": 1}
    with pytest.raises(ValueError, match="duplicate"):
        validate_claim_results({101, 102}, claims + [claims[0]])
    with pytest.raises(ValueError, match="unrecognized"):
        validate_claim_results({101, 102}, [{"host": "tcou", "job_id": 999, "attempt_count": 1}])
