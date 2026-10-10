"""Offline budget-source reconciliation characterization; no DB or HTTP."""
from datetime import datetime, timedelta, timezone

import pytest

from bf4ps.dispatch_budget_model import BudgetEvidence, unified_rolling_usage

NOW = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
IDENTITY = (42, 2, "weapons", "lease-abc")


def evidence(source, *, identity=IDENTITY, occurred_at=NOW, expires_at=None):
    return BudgetEvidence(identity, source, occurred_at, expires_at)


def test_started_and_dispatch_same_attempt_count_once():
    assert unified_rolling_usage([evidence("started"), evidence("dispatch")], at=NOW) == 1


def test_reserved_started_and_dispatch_same_attempt_count_once():
    rows = [
        evidence("reserved", expires_at=NOW + timedelta(minutes=2)),
        evidence("started"),
        evidence("dispatch"),
    ]
    assert unified_rolling_usage(rows, at=NOW) == 1


def test_distinct_attempts_consume_distinct_slots():
    rows = [evidence("started"), evidence("dispatch", identity=(42, 3, "weapons", "lease-def"))]
    assert unified_rolling_usage(rows, at=NOW) == 2


def test_dispatch_without_started_event_still_counts():
    assert unified_rolling_usage([evidence("dispatch")], at=NOW) == 1


def test_expired_reservation_does_not_count():
    assert unified_rolling_usage(
        [evidence("reserved", expires_at=NOW)], at=NOW
    ) == 0


def test_started_record_ages_out_at_exact_hour():
    assert unified_rolling_usage(
        [evidence("started", occurred_at=NOW - timedelta(hours=1))], at=NOW
    ) == 0


def test_unknown_source_fails_closed():
    with pytest.raises(ValueError, match="unknown"):
        unified_rolling_usage([evidence("unexpected")], at=NOW)


def test_naive_clock_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        unified_rolling_usage([], at=NOW.replace(tzinfo=None))


def test_reservation_missing_expiry_rejected():
    with pytest.raises(ValueError, match="expiry"):
        unified_rolling_usage([evidence("reserved")], at=NOW)


def test_late_send_gap_remains_visible_in_accounting_model():
    # A real send delayed beyond its original rolling-hour window is not
    # protected by an admission-time count. This is a characterization,
    # explicitly NOT a successful physical-send guarantee.
    old = evidence("dispatch", occurred_at=NOW - timedelta(hours=1))
    assert unified_rolling_usage([old], at=NOW) == 0
