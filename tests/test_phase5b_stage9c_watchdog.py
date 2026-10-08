"""Pure, no-database regression checks for the Stage 9C watchdog."""
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from scripts.phase5b_stage9c_watchdog import inspect, drain_fleet, IDENTITIES


class FakeResult:
    def __init__(self, rows=None, scalar=None, rowcount=0):
        self.rows = rows or []
        self.value = scalar
        self.rowcount = rowcount

    def scalar_one(self):
        return self.value

    def mappings(self):
        return self

    def all(self):
        return self.rows


class FakeConnection:
    def __init__(self, events=None, registry=None, bad=0, rowcount=3):
        self.events = events or []
        self.registry = registry if registry is not None else [
            dict(collector_uuid=uuid, collector_name=name, hostname=host,
                 egress_key=egress, lane="background", retired_at=None)
            for uuid, (name, host, egress) in IDENTITIES.items()
        ]
        self.bad = bad
        self.rowcount = rowcount
        self.calls = []

    def execute(self, statement, params=None):
        sql = str(statement)
        self.calls.append(sql)
        if "current_database()" in sql:
            return FakeResult(scalar="bf4_playerstats_test")
        if "alembic_version" in sql:
            return FakeResult(scalar="0004_stage9c_supervision_runs")
        if "pg_is_in_recovery()" in sql:
            return FakeResult(scalar=False)
        if "transaction_read_only" in sql:
            return FakeResult(scalar="off")
        if "SELECT now()" in sql:
            return FakeResult(scalar=datetime.now(timezone.utc))
        if "FROM collection_events" in sql:
            return FakeResult(rows=self.events)
        if "COUNT(*) FROM collection_jobs" in sql:
            return FakeResult(scalar=self.bad)
        if "FROM collectors" in sql:
            return FakeResult(rows=self.registry)
        if "UPDATE collectors" in sql:
            return FakeResult(rowcount=self.rowcount)
        raise AssertionError(sql)


CUTOVER = datetime(2026, 10, 8, tzinfo=timezone.utc)


def event(kind, *, key=1, status=None, error=None, age=0):
    return dict(event_id=key * 10 + (kind != "collection_attempt_started"),
                occurred_at=datetime.now(timezone.utc) - timedelta(seconds=age),
                event_type=kind, collector_uuid=next(iter(IDENTITIES)),
                job_id=key, attempt_number=1, http_status=status,
                error_class=error, lane="background", resource="weapons")


def check(conn):
    return inspect(conn, boundary=11558, cutover=CUTOVER, grace_seconds=150)[0]


def test_successful_attempt_is_safe():
    assert check(FakeConnection(events=[event("collection_attempt_started"),
                                        event("collection_success")])) == []


@pytest.mark.parametrize("kind,status,error", [
    ("collection_failure", 403, None),
    ("collection_failure", 429, None),
    ("collection_failure", None, "battlelog_throttle"),
    ("collection_persistence_failure", None, "persistence"),
])
def test_abort_signals(kind, status, error):
    events = [event("collection_attempt_started"), event(kind, status=status, error=error)]
    assert check(FakeConnection(events=events))


def test_transient_503_is_not_abort():
    assert check(FakeConnection(events=[
        event("collection_attempt_started"),
        event("collection_failure", status=503, error="battlelog_http_5xx"),
    ])) == []


def test_recent_inflight_is_tolerated():
    assert check(FakeConnection(events=[event("collection_attempt_started", age=10)])) == []


def test_old_inflight_is_abort():
    assert any("unclosed" in issue for issue in check(FakeConnection(
        events=[event("collection_attempt_started", age=180)])))


def test_bad_provenance_aborts():
    assert any("provenance" in issue for issue in check(FakeConnection(bad=1)))


def test_drain_updates_all_three_only():
    conn = FakeConnection()
    assert drain_fleet(conn) == 3
    assert sum("UPDATE collectors" in sql for sql in conn.calls) == 1


def test_drain_refuses_identity_drift_without_writes():
    conn = FakeConnection()
    conn.registry[0]["egress_key"] = "wrong"
    with pytest.raises(RuntimeError, match="identity drift"):
        drain_fleet(conn)
    assert not any("UPDATE collectors" in sql for sql in conn.calls)


def test_drain_refuses_missing_collector():
    conn = FakeConnection()
    conn.registry.pop()
    with pytest.raises(RuntimeError, match="missing"):
        drain_fleet(conn)
    assert not any("UPDATE collectors" in sql for sql in conn.calls)
