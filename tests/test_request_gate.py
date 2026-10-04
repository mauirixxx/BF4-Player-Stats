import pytest

from bf4ps.request_gate import _validate


def test_gate_rejects_empty_egress_key():
    with pytest.raises(ValueError, match="egress_key"):
        _validate("   ", 1.0)


def test_gate_rejects_negative_interval():
    with pytest.raises(ValueError, match="interval_seconds"):
        _validate("mak-public", -0.1)


def test_gate_rejects_non_finite_interval():
    with pytest.raises(ValueError, match="interval_seconds"):
        _validate("mak-public", float("inf"))


def test_gate_accepts_zero_interval_and_normalizes_key():
    assert _validate(" mak-public ", 0) == "mak-public"
