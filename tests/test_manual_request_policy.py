from datetime import datetime, timedelta, timezone
import pytest
from bf4ps.manual_request_policy import cooldown_remaining, refreshable_resources, RESOURCES

NOW = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)


def test_new_soldier_has_no_cooldown():
    assert cooldown_remaining(last_accepted_at=None, now=NOW) == timedelta(0)


def test_recent_request_waits():
    assert cooldown_remaining(last_accepted_at=NOW-timedelta(minutes=10), now=NOW) == timedelta(minutes=50)


def test_expired_request_does_not_wait():
    assert cooldown_remaining(last_accepted_at=NOW-timedelta(minutes=61), now=NOW) == timedelta(0)


def test_new_soldier_needs_all_resources():
    assert refreshable_resources(last_success={}, now=NOW) == RESOURCES


def test_only_stale_or_missing_resources_refresh():
    stamps = {'detailed': NOW-timedelta(minutes=5), 'weapons': NOW-timedelta(hours=2), 'vehicles': NOW-timedelta(minutes=20)}
    assert refreshable_resources(last_success=stamps, now=NOW) == ('weapons', 'profile')


def test_timezone_naive_input_rejected():
    with pytest.raises(ValueError):
        cooldown_remaining(last_accepted_at=None, now=NOW.replace(tzinfo=None))