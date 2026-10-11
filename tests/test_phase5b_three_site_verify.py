"""Multi-host dry-run report validation tests."""
import pytest
from scripts.phase5b_three_site_coordinator import FleetPlan
from scripts.phase5b_three_site_verify import validate_worker_reports


def sample():
    plan = FleetPlan.build("dryrun_oct10", {"tcou": 3, "kah-01": 3, "hnl-01": 2})
    return plan, [w.report() for w in plan.workers()]


def test_full_eight_worker_reports():
    plan, reports = sample()
    summary = validate_worker_reports(plan, reports)
    assert summary["worker_count"] == summary["unique_collectors"] == 8
    assert summary["hosts"] == ["hnl-01", "kah-01", "tcou"]


@pytest.mark.parametrize("change", [
    lambda reports: reports.pop(),
    lambda reports: reports.append(dict(reports[0])),
    lambda reports: reports[0].update(collector_uuid="00000000-0000-0000-0000-000000000000"),
    lambda reports: reports[0].update(http_requests=1),
    lambda reports: reports[0].update(database_writes=1),
    lambda reports: reports[0].update(host="unknown"),
    lambda reports: reports[0].update(run_id="other"),
    lambda reports: reports[0].update(mode="execute"),
])
def test_rejects_bad_reports(change):
    plan, reports = sample()
    change(reports)
    with pytest.raises(ValueError):
        validate_worker_reports(plan, reports)
