import pytest

from bf4ps.discovery_service import seconds_until_due


def test_seconds_until_due_uses_earliest_job():
    assert seconds_until_due(100.0, 160.0, 400.0) == 60.0
    assert seconds_until_due(100.0, 160.0, 120.0) == 20.0


def test_seconds_until_due_never_returns_negative():
    assert seconds_until_due(100.0, 90.0, 120.0) == 0.0
