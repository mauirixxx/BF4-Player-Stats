"""Offline D2 adversarial timing tests: never transmit HTTP."""
import pytest

from bf4ps.dispatch_timing_adversarial import (
    Attempt, GLOBAL_LIMIT, admission_windows_safe, count_rolling,
    delayed_send_counterexample, physical_windows_safe,
    ttl_check_then_pause_counterexample, worst_case_possible_usage,
)


def test_full_limit_delayed_send_breaks_physical_window():
    attempts = delayed_send_counterexample()
    assert len(attempts) == GLOBAL_LIMIT + 1
    assert admission_windows_safe(attempts)
    assert not physical_windows_safe(attempts)
    assert count_rolling([a.physical_send_at for a in attempts], at=3602) == GLOBAL_LIMIT + 1


def test_small_limit_has_same_counterexample():
    for limit in (1, 2, 10):
        attempts = delayed_send_counterexample(limit=limit)
        assert admission_windows_safe(attempts, limit=limit)
        assert not physical_windows_safe(attempts, limit=limit)


def test_ttl_check_can_precede_unbounded_pause():
    for ttl in (1, 5, 60):
        attempt = ttl_check_then_pause_counterexample(ttl_seconds=ttl)
        assert 1 < ttl or ttl == 1  # check at t=0 is valid for ttl=1
        assert attempt.physical_send_at > attempt.admitted_at + ttl


def test_unknown_send_does_not_age_out_in_fail_closed_accounting():
    attempt = Attempt("unknown", 0, None)
    assert worst_case_possible_usage([attempt], at=3601, unresolved_ids={"unknown"}) == 1
    assert worst_case_possible_usage([attempt], at=1000000, unresolved_ids={"unknown"}) == 1


def test_resolved_old_send_does_age_out():
    attempt = Attempt("resolved", 0, 0)
    assert worst_case_possible_usage([attempt], at=3601, unresolved_ids=set()) == 0


def test_unresolved_and_known_are_both_charged():
    attempts = [Attempt("unknown", 0), Attempt("sent", 3601, 3601)]
    assert worst_case_possible_usage(attempts, at=3601, unresolved_ids={"unknown"}) == 2


def test_window_excludes_left_boundary():
    assert count_rolling([0, 1, 3600], at=3600) == 2


def test_duplicate_identity_refused():
    with pytest.raises(ValueError, match="duplicate"):
        worst_case_possible_usage([Attempt("x", 0), Attempt("x", 1)], at=1, unresolved_ids={"x"})


def test_invalid_limits_and_windows_refused():
    with pytest.raises(ValueError):
        delayed_send_counterexample(limit=0)
    with pytest.raises(ValueError):
        count_rolling([], at=0, window=0)
    with pytest.raises(ValueError):
        ttl_check_then_pause_counterexample(ttl_seconds=0)
