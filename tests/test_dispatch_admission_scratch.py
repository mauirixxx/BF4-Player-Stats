"""Scratch-only SQL admission boundaries; no database or HTTP."""
from unittest.mock import Mock
from uuid import uuid4

import pytest

from bf4ps.dispatch_admission_scratch import SyntheticDispatch, try_synthetic_admission


def candidate():
    return SyntheticDispatch(uuid4(), 100, 1, "weapons", uuid4(), uuid4(), "synthetic", "digest")


def test_refuses_no_transaction():
    conn = Mock()
    conn.in_transaction.return_value = False
    with pytest.raises(RuntimeError, match="transaction required"):
        try_synthetic_admission(conn, candidate())
    conn.execute.assert_not_called()


def test_refuses_invalid_capacity():
    conn = Mock()
    conn.in_transaction.return_value = True
    for capacity in (0, -1, 1297):
        with pytest.raises(ValueError, match="capacity"):
            try_synthetic_admission(conn, candidate(), capacity=capacity)
    conn.execute.assert_not_called()


def test_query_happens_after_lock_and_clock(monkeypatch):
    from bf4ps import dispatch_admission_scratch as mod
    conn = Mock()
    conn.in_transaction.return_value = True
    conn.execute.return_value.scalar_one.return_value = object()
    seen = []

    def fake_usage(c, *, at):
        seen.append(("usage", at))
        return 0

    monkeypatch.setattr(mod, "read_conservative_background_usage", fake_usage)
    assert try_synthetic_admission(conn, candidate(), capacity=1)
    assert conn.execute.call_count == 3
    assert conn.execute.call_args_list[0].args[0] is mod.LOCK
    assert conn.execute.call_args_list[1].args[0] is mod.CLOCK
    assert conn.execute.call_args_list[2].args[0] is mod.INSERT
    assert len(seen) == 1


def test_denied_without_insert(monkeypatch):
    from bf4ps import dispatch_admission_scratch as mod
    conn = Mock()
    conn.in_transaction.return_value = True
    conn.execute.return_value.scalar_one.return_value = object()
    monkeypatch.setattr(mod, "read_conservative_background_usage", lambda c, at: 1)
    assert not try_synthetic_admission(conn, candidate(), capacity=1)
    assert conn.execute.call_count == 2
