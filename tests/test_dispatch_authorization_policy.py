"""Offline policy tests for the proposed shared dispatch authorization."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from bf4ps.dispatch_authorization import (
    DispatchAuthorization,
    DispatchAuthorizationRejected,
    validate_dispatch_authorization,
)

T0 = datetime(2026, 10, 10, 6, 0, tzinfo=timezone.utc)


def permit():
    return DispatchAuthorization(46, 1, uuid4(), uuid4(), T0, T0 + timedelta(seconds=5))


def check(p, when, **overrides):
    params = dict(
        job_id=p.job_id,
        attempt_number=p.attempt_number,
        collector_uuid=p.collector_uuid,
        lease_token=p.lease_token,
    )
    params.update(overrides)
    validate_dispatch_authorization(p, observed_at=when, **params)


def test_within_window_is_accepted():
    p = permit()
    check(p, T0)
    check(p, p.expires_at - timedelta(microseconds=1))


@pytest.mark.parametrize("when", [T0 - timedelta(microseconds=1), T0 + timedelta(seconds=5), T0 + timedelta(hours=1)])
def test_outside_window_rejected(when):
    with pytest.raises(DispatchAuthorizationRejected, match="time window"):
        check(permit(), when)


@pytest.mark.parametrize("field", ["job_id", "attempt_number", "collector_uuid", "lease_token"])
def test_stale_owner_or_attempt_rejected(field):
    p = permit()
    wrong = uuid4() if field in ("collector_uuid", "lease_token") else 99
    with pytest.raises(DispatchAuthorizationRejected, match="ownership"):
        check(p, T0 + timedelta(seconds=1), **{field: wrong})


def test_invalid_interval_rejected():
    p = permit()
    p = DispatchAuthorization(p.job_id, p.attempt_number, p.collector_uuid, p.lease_token, T0, T0)
    with pytest.raises(DispatchAuthorizationRejected, match="interval"):
        check(p, T0)


def test_naive_timestamp_rejected():
    p = permit()
    with pytest.raises(ValueError, match="timezone-aware"):
        check(p, T0.replace(tzinfo=None))


def test_authorization_is_not_an_atomic_handoff():
    """Document limitation: passing check cannot prevent a later OS pause."""
    p = permit()
    check(p, T0 + timedelta(seconds=1))
    # No actual fetch occurs here. A paused process could resume after expiry;
    # the caller must not treat the earlier check as a permanent permission.
    assert T0 + timedelta(hours=1) > p.expires_at
