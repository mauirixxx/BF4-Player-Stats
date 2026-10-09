from datetime import datetime, timedelta, timezone

import pytest

from bf4ps.stage9c_checkpoint_math import observed_rolling_max


START = datetime(2026, 10, 8, 4, 0, tzinfo=timezone.utc)


def events(count, stamp, offset=0):
    return [(i + offset, stamp) for i in range(count)]


def test_cross_boundary_1297():
    rows = events(1296, START - timedelta(minutes=1))
    rows += events(1, START + timedelta(minutes=1), 1296)
    assert observed_rolling_max(rows, supervision_start=START, checkpoint_at=START + timedelta(minutes=2)) == 1297


def test_cross_boundary_1296():
    rows = events(1295, START - timedelta(minutes=1))
    rows += events(1, START + timedelta(minutes=1), 1295)
    assert observed_rolling_max(rows, supervision_start=START, checkpoint_at=START + timedelta(minutes=2)) == 1296


def test_pre_supervision_only_saturated_current_hour():
    rows = events(1297, START - timedelta(minutes=1))
    assert observed_rolling_max(rows, supervision_start=START, checkpoint_at=START) == 1297


def test_exact_hour_expiry():
    rows = events(1297, START - timedelta(minutes=1))
    assert observed_rolling_max(rows, supervision_start=START, checkpoint_at=START + timedelta(minutes=59)) == 0


def test_historical_peak_retained_after_expiry():
    rows = events(1296, START - timedelta(minutes=1))
    rows += events(1, START, 1296)
    assert observed_rolling_max(rows, supervision_start=START, checkpoint_at=START + timedelta(hours=2)) == 1297


def test_pre_supervision_only_expired_peak_not_counted():
    rows = events(1297, START - timedelta(minutes=1))
    assert observed_rolling_max(rows, supervision_start=START, checkpoint_at=START + timedelta(hours=2)) == 0


def test_empty_events():
    assert observed_rolling_max([], supervision_start=START, checkpoint_at=START) == 0


@pytest.mark.parametrize("bad", [START - timedelta(hours=1), START + timedelta(minutes=1)])
def test_refuses_events_outside_window(bad):
    with pytest.raises(ValueError):
        observed_rolling_max(events(1, bad), supervision_start=START, checkpoint_at=START)


def test_refuses_naive_start():
    with pytest.raises(ValueError):
        observed_rolling_max([], supervision_start=START.replace(tzinfo=None), checkpoint_at=START)
