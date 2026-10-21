from datetime import datetime, timezone

import pytest

from bf4ps.discovery import reconciliation_since


def test_initial_reconciliation_uses_activity_window():
    source_now = datetime(2026, 10, 3, 5, 30, tzinfo=timezone.utc)
    assert reconciliation_since(
        None,
        source_now,
        initial_window_hours=24,
        overlap_minutes=15,
    ) == datetime(2026, 10, 2, 5, 30, tzinfo=timezone.utc)


def test_subsequent_reconciliation_uses_watermark_overlap():
    source_now = datetime(2026, 10, 3, 5, 30, tzinfo=timezone.utc)
    previous = datetime(2026, 10, 3, 5, 0, tzinfo=timezone.utc)
    assert reconciliation_since(
        previous,
        source_now,
        initial_window_hours=24,
        overlap_minutes=15,
    ) == datetime(2026, 10, 3, 4, 45, tzinfo=timezone.utc)


def test_reconciliation_rejects_invalid_window():
    now = datetime.now(timezone.utc)
    with pytest.raises(ValueError, match="initial_window_hours"):
        reconciliation_since(None, now, initial_window_hours=0, overlap_minutes=15)


def test_reconciliation_rejects_negative_overlap():
    now = datetime.now(timezone.utc)
    with pytest.raises(ValueError, match="overlap_minutes"):
        reconciliation_since(None, now, initial_window_hours=24, overlap_minutes=-1)
