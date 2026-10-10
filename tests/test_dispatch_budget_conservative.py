"""Offline edge tests for conservative D2 three-source accounting."""
from datetime import datetime, timedelta, timezone

import pytest

from bf4ps.dispatch_budget_conservative import (
    ReconciliationEvidence as E, conservative_background_usage as usage,
)

NOW = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
BASE = dict(job_id=42, attempt_number=2, resource="weapons", lease_token="lease-a")


def row(source, **overrides):
    fields = {**BASE, "source": source, "occurred_at": NOW}
    if source == "reserved":
        fields["expires_at"] = NOW + timedelta(minutes=1)
    fields.update(overrides)
    return E(**fields)


def test_three_complete_sources_are_one_attempt():
    assert usage([row("started"), row("reserved"), row("dispatch")], at=NOW) == 1


def test_null_key_event_cannot_be_deduplicated():
    assert usage([row("started", lease_token=None), row("dispatch")], at=NOW) == 2


def test_multiple_null_events_each_charge_one():
    assert usage([row("started", lease_token=None), row("started", lease_token=None)], at=NOW) == 2


def test_reclaimed_token_is_distinct():
    assert usage([row("started"), row("reserved", lease_token="lease-b")], at=NOW) == 2


def test_duplicate_started_events_are_not_silently_erased():
    assert usage([row("started"), row("started"), row("dispatch")], at=NOW) == 2


def test_timestamp_split_uses_any_active_evidence():
    assert usage([row("started", occurred_at=NOW - timedelta(hours=1)),
                  row("dispatch")], at=NOW) == 1


def test_exact_hour_boundary_is_excluded():
    assert usage([row("dispatch", occurred_at=NOW - timedelta(hours=1))], at=NOW) == 0


def test_expired_reservation_excluded():
    assert usage([row("reserved", expires_at=NOW)], at=NOW) == 0


def test_incomplete_active_reservation_conservatively_charged():
    assert usage([row("reserved", lease_token=None)], at=NOW) == 1


def test_unknown_source_fails_closed():
    with pytest.raises(ValueError, match="unknown source"):
        usage([row("bogus")], at=NOW)


def test_naive_timestamp_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        usage([row("started", occurred_at=NOW.replace(tzinfo=None))], at=NOW)


def test_no_late_send_guarantee():
    assert usage([row("dispatch", occurred_at=NOW - timedelta(hours=2))], at=NOW) == 0
