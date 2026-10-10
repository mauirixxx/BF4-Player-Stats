"""Zero-network reproduction of the committed-start -> fetch handoff.

These are *characterization* tests: they demonstrate the current risk, not
acceptance that dispatch after lease loss is safe. No DB or HTTP is used.
"""
from contextlib import contextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest

from bf4ps import detailed_collector, weapon_collector, vehicle_collector


class StopBeforeNetwork(BaseException):
    """Abort the test at the exact fake outbound dispatch boundary."""


class FakeEngine:
    @contextmanager
    def begin(self):
        yield object()


@pytest.mark.parametrize(
    ("module", "collector_fn", "record_fn", "fetch_fn"),
    [
        (detailed_collector, "collect_one_detailed_job", "_record_detailed_attempt_started", "fetch_detailed_stats"),
        (weapon_collector, "collect_one_weapon_job", "_record_attempt_started", "fetch_weapon_stats"),
        (vehicle_collector, "collect_one_vehicle_job", "_record_vehicle_attempt_started", "fetch_vehicle_stats"),
    ],
)
def test_post_commit_lease_loss_does_not_block_fake_dispatch(
    monkeypatch, module, collector_fn, record_fn, fetch_fn
):
    """Current behavior: losing lease after committed start does not stop fetch.

    This test must be replaced by a fail-closed dispatch invariant before
    production authorization; it deliberately records the unsafe reachability.
    """
    from bf4ps.collection_jobs import ClaimedJob

    owner = uuid4()
    job = ClaimedJob(
        job_id=46, soldier_id=46, resource=module.__name__.split("_")[0],
        lane="background", attempt_count=1, collector_uuid=owner, lease_token=uuid4(),
    )
    events = []
    state = {"lease_valid": True}

    monkeypatch.setattr(module, "claim_production_background_job", lambda *a, **k: job)
    monkeypatch.setattr(module, "mark_job_running", lambda *a, **k: True)
    monkeypatch.setattr(module, "_soldier_identity", lambda *a, **k: (236753552, "pc"))
    monkeypatch.setattr(module, "reserve_request_slot", lambda *a, **k: SimpleNamespace(wait_seconds=0))

    def record_start(*a, **k):
        assert state["lease_valid"]
        events.append("start_committed")
        # Deterministic pause/resume: lease expires and a new owner takes over
        # immediately after the durable-start transaction returns.
        state["lease_valid"] = False
        events.append("lease_lost")

    def fake_fetch(*a, **k):
        events.append("fetch_reached")
        raise StopBeforeNetwork()

    monkeypatch.setattr(module, record_fn, record_start)
    monkeypatch.setattr(module, fetch_fn, fake_fetch)
    identity = module.CollectorIdentity(owner, "scratch-owner", "fake-host", "fake-egress", "background")

    with pytest.raises(StopBeforeNetwork):
        getattr(module, collector_fn)(
            FakeEngine(), identity=identity, request_interval_seconds=1.0,
            enforce_production_budget=True,
        )

    assert events == ["start_committed", "lease_lost", "fetch_reached"]
