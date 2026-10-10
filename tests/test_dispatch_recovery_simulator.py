"""Deterministic crash and restart tests; no database or network."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from bf4ps.dispatch_simulator import DispatchDenied, Submission
from bf4ps.dispatch_recovery_simulator import (
    DispatchPhase, DurableDispatchState, RecoveryAuthority, SimulatedCrash,
)

T0 = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)


def request(job=1, attempt=1, resource="detailed"):
    return Submission(job, attempt, resource, uuid4(), uuid4(), "mak")


def admit(authority, r, at=T0):
    return authority.admit(r, at=at, owns_lease=lambda *_: True)


def test_crash_before_admission_has_no_effect():
    state = DurableDispatchState()
    r = request()
    assert RecoveryAuthority(state).phase(r) is None
    assert not state.entries


def test_crash_after_admission_before_send_reuses_no_new_capacity():
    state = DurableDispatchState(budget_limit=1)
    r = request()
    assert admit(RecoveryAuthority(state), r)
    restarted = RecoveryAuthority(state)
    assert not admit(restarted, r)
    with pytest.raises(DispatchDenied, match="budget"):
        admit(restarted, request(job=2))
    assert restarted.phase(r) is DispatchPhase.ADMITTED


def test_crash_after_may_have_sent_mark_fails_closed():
    state = DurableDispatchState()
    r = request()
    authority = RecoveryAuthority(state)
    admit(authority, r)
    with pytest.raises(SimulatedCrash):
        authority.send(r, fake_transport=lambda _: pytest.fail("fake send reached"), crash_after_mark=True)
    restarted = RecoveryAuthority(state)
    calls = []
    assert not restarted.send(r, fake_transport=calls.append)
    assert calls == []
    assert restarted.phase(r) is DispatchPhase.MAY_HAVE_SENT


@pytest.mark.parametrize("resource", ["detailed", "weapons", "vehicles"])
def test_lost_acknowledgment_never_replays(resource):
    state = DurableDispatchState()
    r = request(resource=resource)
    authority = RecoveryAuthority(state)
    admit(authority, r)
    calls = []
    def fake_send(value):
        calls.append(value)
        raise SimulatedCrash("lost acknowledgement")
    with pytest.raises(SimulatedCrash):
        authority.send(r, fake_transport=fake_send)
    assert RecoveryAuthority(state).phase(r) is DispatchPhase.MAY_HAVE_SENT
    assert not RecoveryAuthority(state).send(r, fake_transport=calls.append)
    assert calls == [r]


def test_acknowledged_request_never_replays():
    state = DurableDispatchState()
    r = request()
    authority = RecoveryAuthority(state)
    admit(authority, r)
    calls = []
    assert authority.send(r, fake_transport=calls.append)
    assert not RecoveryAuthority(state).send(r, fake_transport=calls.append)
    assert calls == [r]
    assert RecoveryAuthority(state).phase(r) is DispatchPhase.ACKNOWLEDGED


def test_budget_recovers_at_exact_hour_boundary():
    state = DurableDispatchState(budget_limit=1)
    admit(RecoveryAuthority(state), request())
    later = RecoveryAuthority(state)
    with pytest.raises(DispatchDenied):
        admit(later, request(job=2), at=T0 + timedelta(hours=1, microseconds=-1))
    assert admit(later, request(job=3), at=T0 + timedelta(hours=1))


def test_stale_lease_rejected_without_admission():
    state = DurableDispatchState()
    r = request()
    with pytest.raises(DispatchDenied, match="stale"):
        RecoveryAuthority(state).admit(r, at=T0, owns_lease=lambda *_: False)
    assert not state.entries
