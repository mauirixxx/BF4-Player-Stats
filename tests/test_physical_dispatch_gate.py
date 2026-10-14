"""Focused fail-closed tests for the inert production dispatch admission primitive.

These do not substitute for multi-connection PostgreSQL concurrency tests.
"""
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from bf4ps.physical_dispatch_gate import (
    PHYSICAL_DISPATCHES_PER_HOUR,
    PhysicalDispatchBudgetExhausted,
    authorize_physical_dispatch,
)


class _Scalar:
    def __init__(self, value):
        self.value = value

    def scalar_one(self):
        return self.value


class _FakeConnection:
    def __init__(self, used=0, isolation="READ COMMITTED"):
        self.used = used
        self.isolation = isolation
        self.calls = []
        self.now = datetime(2026, 10, 14, tzinfo=timezone.utc)

    def get_isolation_level(self):
        return self.isolation

    def execute(self, statement, params=None):
        sql = str(statement)
        self.calls.append((sql, params))
        if "clock_timestamp()" in sql and sql.lstrip().upper().startswith("SELECT"):
            return _Scalar(self.now)
        if "FROM runtime_budgets" in sql:
            return _Scalar(PHYSICAL_DISPATCHES_PER_HOUR)
        if "COUNT(*)" in sql:
            return _Scalar(self.used)
        return _Scalar(None)


def _authorize(conn, **overrides):
    args = dict(
        job_id=1, attempt_number=1, request_ordinal=1,
        resource="profile", lease_token=uuid4(), collector_uuid=uuid4(),
        egress_key="rnt-01", lane="background", payload_fingerprint="test-payload",
    )
    args.update(overrides)
    return authorize_physical_dispatch(conn, **args)


def test_1295_used_admits_one_and_charges_ledger():
    conn = _FakeConnection(used=PHYSICAL_DISPATCHES_PER_HOUR - 1)
    permit = _authorize(conn)
    assert permit.remaining == 0
    assert any("INSERT INTO outbound_dispatches" in sql for sql, _ in conn.calls)
    assert any("pg_advisory_xact_lock" in sql for sql, _ in conn.calls)


def test_1296_used_denies_without_insert():
    conn = _FakeConnection(used=PHYSICAL_DISPATCHES_PER_HOUR)
    with pytest.raises(PhysicalDispatchBudgetExhausted):
        _authorize(conn)
    assert not any("INSERT INTO outbound_dispatches" in sql for sql, _ in conn.calls)


def test_fail_closed_on_non_read_committed_transaction():
    conn = _FakeConnection(isolation="REPEATABLE READ")
    with pytest.raises(RuntimeError, match="READ COMMITTED"):
        _authorize(conn)
    assert conn.calls == []


def test_invalid_request_ordinal_never_touches_db():
    conn = _FakeConnection()
    with pytest.raises(ValueError):
        _authorize(conn, request_ordinal=0)
    assert conn.calls == []


def test_all_lanes_count_against_one_fleet_window():
    for lane in ("background", "interactive"):
        conn = _FakeConnection(used=PHYSICAL_DISPATCHES_PER_HOUR)
        with pytest.raises(PhysicalDispatchBudgetExhausted):
            _authorize(conn, lane=lane)
