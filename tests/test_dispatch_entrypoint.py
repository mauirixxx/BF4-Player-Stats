"""Shared dispatch entry-point behavior with injected fake transport only."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from bf4ps.dispatch_authorization import DispatchAuthorization, DispatchAuthorizationRejected
from bf4ps.dispatch_entrypoint import dispatch_with_authorization


@pytest.fixture
def authorization():
    now = datetime(2026, 10, 10, 6, tzinfo=timezone.utc)
    return DispatchAuthorization(46, 1, uuid4(), uuid4(), now, now + timedelta(seconds=5))


def call(permit, observed_at, transport, **overrides):
    kwargs = dict(
        job_id=permit.job_id,
        attempt_number=permit.attempt_number,
        collector_uuid=permit.collector_uuid,
        lease_token=permit.lease_token,
    )
    kwargs.update(overrides)
    return dispatch_with_authorization(
        permit, observed_at=observed_at, transport=transport, **kwargs
    )


def test_valid_authorization_invokes_transport_exactly_once(authorization):
    called = []
    assert call(
        authorization, authorization.issued_at, lambda: called.append("fake") or "ok"
    ) == "ok"
    assert called == ["fake"]


@pytest.mark.parametrize("offset", [-1, 5, 3600])
def test_expired_or_premature_authorization_never_invokes_transport(authorization, offset):
    called = []
    with pytest.raises(DispatchAuthorizationRejected):
        call(authorization, authorization.issued_at + timedelta(seconds=offset), lambda: called.append("fake"))
    assert called == []


def test_stale_lease_token_never_invokes_transport(authorization):
    called = []
    with pytest.raises(DispatchAuthorizationRejected, match="ownership"):
        call(
            authorization,
            authorization.issued_at + timedelta(seconds=1),
            lambda: called.append("fake"),
            lease_token=uuid4(),
        )
    assert called == []


def test_fake_transport_exception_propagates(authorization):
    def fake_transport():
        raise LookupError("fake failure")
    with pytest.raises(LookupError, match="fake failure"):
        call(authorization, authorization.issued_at, fake_transport)


def test_post_validation_pause_remains_unfenced(authorization):
    """Document the exact remaining gap; do not claim strict dispatch safety."""
    called = []
    def paused_transport():
        # The process could have been suspended after the policy check.
        resumed_at = authorization.expires_at + timedelta(hours=1)
        assert resumed_at > authorization.expires_at
        called.append("late fake transport")
    call(authorization, authorization.issued_at, paused_transport)
    assert called == ["late fake transport"]
