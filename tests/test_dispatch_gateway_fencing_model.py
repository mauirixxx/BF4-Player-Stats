"""Offline gateway fencing model tests; no network and no DB."""
import pytest

from bf4ps.dispatch_gateway_fencing_model import FencedGatewayModel


def test_one_handoff_one_transmission():
    model = FencedGatewayModel(2)
    assert model.reserve("a", at=0, generation=1)
    assert model.handoff("a", generation=1)
    assert not model.handoff("a", generation=1)
    assert model.transmit("a", at=1, generation=1)
    assert not model.transmit("a", at=2, generation=1)
    assert model.burden(at=2) == 1


def test_old_generation_cannot_transmit_after_fence():
    model = FencedGatewayModel(2)
    assert model.reserve("old", at=0, generation=1)
    assert model.handoff("old", generation=1)
    assert model.crash_and_fence() == 2
    assert not model.transmit("old", at=3602, generation=1)
    assert not model.handoff("old", generation=1)
    assert not model.reserve("new-old", at=3602, generation=1)
    assert model.burden(at=3602) == 1


def test_ambiguous_old_attempt_remains_charged():
    model = FencedGatewayModel(1)
    assert model.reserve("old", at=0, generation=1)
    assert model.handoff("old", generation=1)
    model.timeout("old")
    model.crash_and_fence()
    assert model.burden(at=100000) == 1
    assert not model.reserve("new", at=100000, generation=2)


def test_new_generation_can_use_remaining_capacity():
    model = FencedGatewayModel(2)
    assert model.reserve("old", at=0, generation=1)
    model.crash_and_fence()
    assert model.reserve("new", at=3602, generation=2)
    assert model.burden(at=3602) == 2


def test_replay_after_success_refused():
    model = FencedGatewayModel(1)
    assert model.reserve("a", at=0, generation=1)
    assert model.handoff("a", generation=1)
    assert model.transmit("a", at=0, generation=1)
    with pytest.raises(ValueError, match="fresh"):
        model.reserve("a", at=3601, generation=1)


def test_wrong_owner_cannot_handoff_or_transmit():
    model = FencedGatewayModel(2)
    assert model.reserve("a", at=0, generation=1)
    assert not model.handoff("missing", generation=1)
    assert not model.transmit("a", at=0, generation=1)


def test_old_fence_does_not_release_uncertainty():
    model = FencedGatewayModel(1)
    assert model.reserve("a", at=0, generation=1)
    model.crash_and_fence()
    assert model.burden(at=99999) == 1
