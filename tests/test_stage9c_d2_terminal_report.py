"""Offline tests for the read-only D2 terminal report."""
from datetime import datetime, timedelta, timezone

from scripts.stage9c_d2_terminal_report import classify_job


def row(**overrides):
    base = dict(starts=0, successes=0, queued=True, queue_status="pending",
                lease_expires_at=None)
    base.update(overrides)
    return base


def test_durable_success_requires_dequeued_job():
    now = datetime.now(timezone.utc)
    assert classify_job(row(starts=1, successes=1, queued=False), now) == "durable_success"
    assert classify_job(row(starts=1, successes=1), now) == "success_but_still_queued"


def test_pending_and_expired_running_lease_are_not_http_success():
    now = datetime.now(timezone.utc)
    assert classify_job(row(), now) == "pending_without_physical_start"
    assert classify_job(row(queue_status="running", lease_expires_at=now - timedelta(seconds=1)), now) == "expired_running_lease"
    assert classify_job(row(queue_status="running", lease_expires_at=now + timedelta(seconds=1)), now) == "running_without_physical_start"


def test_physical_start_without_success_is_not_automatically_replayed():
    now = datetime.now(timezone.utc)
    assert classify_job(row(starts=1, successes=0), now) == "physical_start_without_success"


def test_duplicate_or_inconsistent_events_are_anomalies():
    now = datetime.now(timezone.utc)
    assert classify_job(row(starts=2, successes=1), now) == "anomalous_events"
    assert classify_job(row(starts=0, successes=1), now) == "anomalous_events"

def test_terminal_outcome_discrepancy_is_not_silent():
    from unittest.mock import MagicMock, patch
    from scripts import stage9c_d2_terminal_report as report
    now = datetime.now(timezone.utc)
    run = {"run_id": report.RUN_ID, "state": "completed",
           "baseline_event_id": report.BASELINE_EVENT}
    rounds = [{"round_number": n, "state": "completed"} for n in range(1, 13)]
    jobs = [{"round_number": n, "job_id": (n - 1) * 9 + i,
             "soldier_id": i, "outcome": "success", "queue_status": None,
             "lease_expires_at": None, "queued": False, "starts": 1,
             "successes": 1} for n in range(1, 13) for i in range(1, 10)]
    conn = MagicMock()
    def configure():
        results = [MagicMock(), MagicMock(), MagicMock()]
        results[0].mappings.return_value.one_or_none.return_value = run
        results[1].mappings.return_value.all.return_value = rounds
        results[2].mappings.return_value.all.return_value = jobs
        conn.execute.side_effect = results
    configure()
    with patch.object(report, "guard"):
        baseline = report.inspect_terminal(conn, now=now)
    assert baseline["complete"] is True
    assert baseline["outcome_discrepancies"] == []
    jobs[45]["outcome"] = "pending"
    configure()
    with patch.object(report, "guard"):
        changed = report.inspect_terminal(conn, now=now)
    assert changed["complete"] is False
    assert changed["outcome_discrepancies"][0]["job_id"] == 46
