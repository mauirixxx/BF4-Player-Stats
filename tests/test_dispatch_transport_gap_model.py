"""Adversarial transport boundary tests; entirely offline."""
import pytest

from bf4ps.dispatch_transport_gap_model import (
    FencingScenario, conservative_fencing_resolution,
    post_check_pause_counterexample,
)


def test_valid_generation_check_does_not_prevent_post_fence_send():
    schedule = post_check_pause_counterexample()
    assert schedule.check_was_valid()
    assert schedule.send_after_fence()


def test_arbitrary_pause_still_breaks_check_then_send():
    for delay in (2, 3602, 86400):
        schedule = post_check_pause_counterexample(pause_seconds=delay)
        assert schedule.check_was_valid()
        assert schedule.send_after_fence()


def test_fence_does_not_retract_queued_transport_write():
    scenario = FencingScenario()
    scenario.submit_old_write()
    scenario.fence_old_generation()
    assert scenario.active_generation == 2
    assert scenario.drain_queued_write()
    assert scenario.old_write_transmitted


def test_queued_write_replay_does_not_repeat_in_model():
    scenario = FencingScenario()
    scenario.submit_old_write()
    scenario.fence_old_generation()
    assert scenario.drain_queued_write()
    assert not scenario.drain_queued_write()


def test_cannot_submit_after_fencing():
    scenario = FencingScenario()
    scenario.fence_old_generation()
    with pytest.raises(ValueError, match="fenced"):
        scenario.submit_old_write()


def test_queued_write_must_remain_uncertain_without_transport_proof():
    assert not conservative_fencing_resolution(
        old_write_queued=True, transport_drained_proven=False
    )
    assert conservative_fencing_resolution(
        old_write_queued=True, transport_drained_proven=True
    )


def test_unqueued_attempt_may_be_resolved_under_explicit_assumption():
    assert conservative_fencing_resolution(
        old_write_queued=False, transport_drained_proven=False
    )


def test_invalid_delay_refused():
    with pytest.raises(ValueError):
        post_check_pause_counterexample(pause_seconds=1)
