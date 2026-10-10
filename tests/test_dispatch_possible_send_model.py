"""Pure offline possible-send accounting; no transport."""
import pytest

from bf4ps.dispatch_possible_send_model import PossibleSendAuthority


def test_ambiguous_attempt_blocks_capacity_indefinitely():
    model = PossibleSendAuthority(1)
    assert model.reserve("a", at=0)
    model.ambiguous_timeout("a")
    assert not model.reserve("b", at=3601)
    assert not model.reserve("b", at=1000000)


def test_confirmed_send_ages_out_only_after_full_window():
    model = PossibleSendAuthority(1)
    assert model.reserve("a", at=0)
    model.confirm_send("a", sent_at=1)
    assert not model.reserve("b", at=3600)
    assert model.reserve("b", at=3601)


def test_resolved_no_send_releases_capacity_only_by_explicit_proof():
    model = PossibleSendAuthority(1)
    assert model.reserve("a", at=0)
    model.prove_no_send_possible("a")
    assert model.reserve("b", at=0)


def test_duplicate_identity_cannot_be_reused():
    model = PossibleSendAuthority(2)
    assert model.reserve("a", at=0)
    with pytest.raises(ValueError, match="fresh"):
        model.reserve("a", at=0)
    model.confirm_send("a", sent_at=0)
    with pytest.raises(ValueError, match="fresh"):
        model.reserve("a", at=3601)


def test_uncertain_send_and_recent_confirmed_send_add():
    model = PossibleSendAuthority(2)
    assert model.reserve("a", at=0)
    assert model.reserve("b", at=0)
    model.confirm_send("a", sent_at=0)
    assert model.burden(1) == 2
    assert not model.reserve("c", at=1)


def test_invalid_resolution_refused():
    model = PossibleSendAuthority(1)
    with pytest.raises(ValueError):
        model.ambiguous_timeout("missing")
    with pytest.raises(ValueError):
        model.confirm_send("missing", sent_at=0)
    with pytest.raises(ValueError):
        model.prove_no_send_possible("missing")


def test_invalid_capacity_refused():
    with pytest.raises(ValueError):
        PossibleSendAuthority(0).reserve("a", at=0)
