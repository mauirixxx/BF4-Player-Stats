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
