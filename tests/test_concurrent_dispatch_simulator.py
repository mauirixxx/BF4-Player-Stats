"""Concurrent admission behavior with threads and fake clocks; no HTTP or DB."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from uuid import uuid4

import pytest

from bf4ps.concurrent_dispatch_simulator import SharedAdmissionLedger
from bf4ps.dispatch_simulator import DispatchDenied, Submission

NOW = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)


def request(job_id, resource="detailed", attempt=1, token=None, egress="mak"):
    return Submission(job_id, attempt, resource, uuid4(), token or uuid4(), egress)


def contend(ledger, requests, *, at=NOW, owner=lambda *_: True):
    barrier = Barrier(len(requests))
    def runner(r):
        barrier.wait(timeout=5)
        try:
            return ledger.admit(r, at=at, owns_lease=owner)
        except DispatchDenied:
            return "denied"
    with ThreadPoolExecutor(max_workers=len(requests)) as pool:
        return list(pool.map(runner, requests))


def test_two_dispatchers_last_slot_exactly_one_winner():
    ledger = SharedAdmissionLedger(limit=1)
    outcomes = contend(ledger, [request(1), request(2)])
    assert sorted(outcomes, key=str) == [True, "denied"]
    assert len(ledger.admissions) == 1


@pytest.mark.parametrize("resource", ["detailed", "weapons", "vehicles"])
def test_duplicate_identity_across_contenders_only_one_admission(resource):
    ledger = SharedAdmissionLedger(limit=1)
    r = request(7, resource)
    outcomes = contend(ledger, [r, r])
    assert outcomes.count(True) == 1
    assert outcomes.count(False) == 1
    assert len(ledger.admissions) == 1


def test_many_contenders_cannot_exceed_global_budget():
    ledger = SharedAdmissionLedger(limit=3)
    requests = [request(i, egress=("mak", "hnl", "kah")[i % 3]) for i in range(12)]
    outcomes = contend(ledger, requests)
    assert outcomes.count(True) == 3
    assert outcomes.count("denied") == 9
    assert len(ledger.admissions) == 3


def test_replay_after_lost_acknowledgment_never_allocates_new_slot():
    ledger = SharedAdmissionLedger(limit=1)
    r = request(1)
    assert ledger.admit(r, at=NOW, owns_lease=lambda *_: True)
    # Even after the original lease expires, replay is not a new grant.
    assert not ledger.admit(r, at=NOW + timedelta(seconds=30), owns_lease=lambda *_: False)
    assert len(ledger.admissions) == 1


def test_stale_owner_cannot_consume_last_slot():
    ledger = SharedAdmissionLedger(limit=1)
    stale = request(1)
    current = request(2)
    outcomes = contend(ledger, [stale, current], owner=lambda r, _: r == current)
    assert outcomes.count(True) == 1
    assert outcomes.count("denied") == 1
    assert list(ledger.admissions) == [current.key]


def test_rolling_hour_cutoff_is_half_open():
    ledger = SharedAdmissionLedger(limit=1)
    assert ledger.admit(request(1), at=NOW, owns_lease=lambda *_: True)
    with pytest.raises(DispatchDenied, match="budget"):
        ledger.admit(request(2), at=NOW + timedelta(hours=1, microseconds=-1), owns_lease=lambda *_: True)
    assert ledger.admit(request(3), at=NOW + timedelta(hours=1), owns_lease=lambda *_: True)


def test_naive_clock_is_rejected_without_mutation():
    ledger = SharedAdmissionLedger(limit=1)
    with pytest.raises(ValueError, match="timezone-aware"):
        ledger.admit(request(1), at=NOW.replace(tzinfo=None), owns_lease=lambda *_: True)
    assert ledger.admissions == {}
