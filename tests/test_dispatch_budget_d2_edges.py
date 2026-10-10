"""Offline D2 boundary cases for the existing pure budget accounting model."""
from datetime import datetime, timedelta, timezone

from bf4ps.dispatch_budget_model import BudgetEvidence, unified_rolling_usage

NOW = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
KEY = (71, 4, "weapons", "lease-x")


def evidence(source, time, key=KEY, expiry=None):
    return BudgetEvidence(key, source, time, expiry)


def test_old_start_recent_dispatch_counts():
    records = [evidence("started", NOW - timedelta(hours=2)), evidence("dispatch", NOW)]
    assert unified_rolling_usage(records, at=NOW) == 1


def test_two_recent_sources_count_once():
    records = [evidence("started", NOW - timedelta(minutes=59)), evidence("dispatch", NOW)]
    assert unified_rolling_usage(records, at=NOW) == 1


def test_future_dispatch_not_counted_early():
    assert unified_rolling_usage([evidence("dispatch", NOW + timedelta(seconds=1))], at=NOW) == 0


def test_exact_hour_boundary_excluded():
    assert unified_rolling_usage([evidence("dispatch", NOW - timedelta(hours=1))], at=NOW) == 0


def test_different_lease_token_is_different_identity():
    records = [evidence("dispatch", NOW), evidence("dispatch", NOW, (71, 4, "weapons", "lease-y"))]
    assert unified_rolling_usage(records, at=NOW) == 2


def test_active_reservation_counts_when_start_aged_out():
    records = [
        evidence("started", NOW - timedelta(hours=2)),
        evidence("reserved", NOW - timedelta(hours=2), expiry=NOW + timedelta(seconds=1)),
    ]
    assert unified_rolling_usage(records, at=NOW) == 1
