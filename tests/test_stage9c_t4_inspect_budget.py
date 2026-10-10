from datetime import datetime, timedelta, timezone

import pytest

from scripts.phase5b_stage9c_t4_inspect_budget import expected_t4_usage, verify_t4_usage


NOW = datetime(2026, 10, 10, 6, 20, tzinfo=timezone.utc)


def test_active_unstarted_reservation_counts_final_slot():
    assert expected_t4_usage(lease_expires_at=NOW + timedelta(seconds=1), observed_at=NOW) == 1296
    assert "1296/1296" in verify_t4_usage(observed_total=1296, lease_expires_at=NOW + timedelta(seconds=1), observed_at=NOW)


def test_expired_unstarted_reservation_is_not_counted():
    assert expected_t4_usage(lease_expires_at=NOW - timedelta(seconds=1), observed_at=NOW) == 1295
    assert "expired" in verify_t4_usage(observed_total=1295, lease_expires_at=NOW - timedelta(seconds=1), observed_at=NOW)


def test_exact_expiry_is_excluded():
    assert expected_t4_usage(lease_expires_at=NOW, observed_at=NOW) == 1295


@pytest.mark.parametrize("observed,offset", [(1295, 1), (1296, -1)])
def test_incorrect_accounting_still_fails(observed, offset):
    with pytest.raises(AssertionError, match="budget mismatch"):
        verify_t4_usage(observed_total=observed, lease_expires_at=NOW + timedelta(seconds=offset), observed_at=NOW)


def test_naive_timestamps_refused():
    with pytest.raises(ValueError, match="timezone-aware"):
        expected_t4_usage(lease_expires_at=NOW.replace(tzinfo=None), observed_at=NOW)
