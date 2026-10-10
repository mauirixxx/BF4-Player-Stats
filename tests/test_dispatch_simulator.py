"""Offline mediated-dispatch model: no PostgreSQL or HTTP."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from bf4ps.dispatch_simulator import DispatchDenied, FakeDispatchAuthority, Submission

T0 = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)


def req(resource="detailed", job_id=1, owner=None, token=None, egress="mak"):
    return Submission(job_id, 1, resource, owner or uuid4(), token or uuid4(), egress)


def test_replay_is_not_sent_twice():
    gate = FakeDispatchAuthority()
    r = req()
    sent = []
    send = lambda request: sent.append(request)
    assert gate.submit(r, at=T0, owns_lease=lambda *_: True, fake_transport=send)
    assert not gate.submit(r, at=T0, owns_lease=lambda *_: True, fake_transport=send)
    assert sent == [r]


@pytest.mark.parametrize("resource", ["detailed", "weapons", "vehicles"])
def test_stale_worker_cannot_reach_fake_transport(resource):
    gate = FakeDispatchAuthority()
    sent = []
    with pytest.raises(DispatchDenied, match="stale owner"):
        gate.submit(req(resource), at=T0, owns_lease=lambda *_: False, fake_transport=sent.append)
    assert sent == []


def test_budget_is_global_across_egress_and_resource():
    gate = FakeDispatchAuthority(limit=2)
    sent = []
    for r in (req("detailed", 1, egress="mak"), req("weapons", 2, egress="hnl")):
        assert gate.submit(r, at=T0, owns_lease=lambda *_: True, fake_transport=sent.append)
    with pytest.raises(DispatchDenied, match="budget"):
        gate.submit(req("vehicles", 3, egress="kah"), at=T0, owns_lease=lambda *_: True, fake_transport=sent.append)
    assert len(sent) == 2


def test_rolling_hour_exact_boundary():
    gate = FakeDispatchAuthority(limit=1)
    sent = []
    gate.submit(req(job_id=1), at=T0, owns_lease=lambda *_: True, fake_transport=sent.append)
    with pytest.raises(DispatchDenied):
        gate.submit(req(job_id=2), at=T0 + timedelta(hours=1, microseconds=-1), owns_lease=lambda *_: True, fake_transport=sent.append)
    gate.submit(req(job_id=3), at=T0 + timedelta(hours=1), owns_lease=lambda *_: True, fake_transport=sent.append)
    assert len(sent) == 2


def test_database_unavailable_fails_closed():
    gate = FakeDispatchAuthority(available=False)
    sent = []
    with pytest.raises(DispatchDenied, match="unavailable"):
        gate.submit(req(), at=T0, owns_lease=lambda *_: True, fake_transport=sent.append)
    assert not sent


def test_replacement_attempt_with_new_token_can_dispatch():
    gate = FakeDispatchAuthority()
    sent = []
    old = req()
    replacement = Submission(old.job_id, 2, old.resource, uuid4(), uuid4(), old.egress_key)
    with pytest.raises(DispatchDenied):
        gate.submit(old, at=T0, owns_lease=lambda r, _: r == replacement, fake_transport=sent.append)
    assert gate.submit(replacement, at=T0, owns_lease=lambda r, _: r == replacement, fake_transport=sent.append)
    assert sent == [replacement]


def test_invalid_clock_rejected():
    gate = FakeDispatchAuthority()
    with pytest.raises(ValueError, match="timezone-aware"):
        gate.submit(req(), at=T0.replace(tzinfo=None), owns_lease=lambda *_: True, fake_transport=lambda _: None)
