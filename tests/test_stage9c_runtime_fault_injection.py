"""Stage 9C runtime behavioral fault injection: no PostgreSQL or systemd calls."""
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4
import sys

import pytest

from scripts import phase5b_stage9c_watchdog as watchdog
from scripts import phase5b_stage9c_local_guard as guard
from bf4ps.stage9c_supervision import CUTOVER_AT, BOUNDARY_EVENT_ID


class TransactionEngine:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0
        self.disposed = False
        self.actions = []

    @contextmanager
    def begin(self):
        staged = []
        try:
            yield staged
        except Exception:
            self.rollbacks += 1
            raise
        else:
            self.actions.extend(staged)
            self.commits += 1

    def dispose(self):
        self.disposed = True


def run_watchdog(monkeypatch, *, issues, fail_drain=False, fail_inspection=False, fail_fallback=False):
    engine = TransactionEngine()
    monkeypatch.setattr(watchdog, "STOP", False)
    monkeypatch.setattr(watchdog, "database_url", lambda: "postgresql+psycopg://unused/unused")
    monkeypatch.setattr(watchdog.signal, "signal", lambda *a: None)
    monkeypatch.setattr(watchdog, "create_engine", lambda *a, **kw: engine)
    monkeypatch.setattr(watchdog, "validate_target", lambda conn: None)
    monkeypatch.setattr(watchdog, "require_guard_lease", lambda conn, run_id: {"started_at": datetime.now(timezone.utc)})

    def inspect(conn, **kwargs):
        if fail_inspection:
            raise RuntimeError("simulated inspection failure")
        return issues, 0, 0, 0

    def renew(conn, **kwargs):
        conn.append("renew")

    def abort(conn, **kwargs):
        if fail_fallback and engine.rollbacks:
            raise RuntimeError("simulated fallback abort failure")
        conn.append("abort")

    def drain(conn):
        if fail_drain:
            raise RuntimeError("simulated drain failure")
        conn.append("drain")
        return 3

    monkeypatch.setattr(watchdog, "inspect", inspect)
    monkeypatch.setattr(watchdog, "renew_after_inspection", renew)
    monkeypatch.setattr(watchdog, "abort_owned_run", abort)
    monkeypatch.setattr(watchdog, "drain_fleet", drain)
    monkeypatch.setattr(sys, "argv", [
        "watchdog", "--run-id", str(uuid4()), "--watchdog-owner", str(uuid4()),
        "--watchdog-generation", "1", "--cutover-at", CUTOVER_AT,
        "--since-event-id", str(BOUNDARY_EVENT_ID), "--armed", "--once",
    ])
    return watchdog.main(), engine


def test_healthy_inspection_renews_only(monkeypatch):
    result, engine = run_watchdog(monkeypatch, issues=[])
    assert result == 0
    assert engine.actions == ["renew"]
    assert (engine.commits, engine.rollbacks, engine.disposed) == (1, 0, True)


def test_confirmed_fault_aborts_and_drains_atomically(monkeypatch):
    result, engine = run_watchdog(monkeypatch, issues=["simulated 429"])
    assert result == 2
    assert engine.actions == ["abort", "drain"]
    assert engine.commits == 1


def test_drain_failure_rolls_back_combined_transaction_then_commits_fenced_abort(monkeypatch):
    result, engine = run_watchdog(monkeypatch, issues=["simulated 429"], fail_drain=True)
    assert result == 2
    assert engine.actions == ["abort"]  # Never claim a completed fleet drain.
    assert (engine.commits, engine.rollbacks) == (1, 1)


def test_failed_fallback_never_claims_abort_or_drain(monkeypatch):
    result, engine = run_watchdog(
        monkeypatch, issues=["simulated 429"], fail_drain=True, fail_fallback=True,
    )
    assert result == 3
    assert engine.actions == []
    assert (engine.commits, engine.rollbacks) == (0, 2)


def test_inspection_exception_does_not_renew(monkeypatch):
    result, engine = run_watchdog(monkeypatch, issues=[], fail_inspection=True)
    assert result == 3
    assert engine.actions == []
    assert engine.rollbacks == 1


def test_guard_db_failure_stops_local_units(monkeypatch):
    class BrokenConnection:
        def __enter__(self):
            raise RuntimeError("simulated database outage")
        def __exit__(self, *args):
            return False

    class Engine:
        def connect(self):
            return BrokenConnection()
        def dispose(self):
            pass

    stopped = []
    monkeypatch.setattr(guard, "STOP", False)
    monkeypatch.setattr(guard, "database_url", lambda: "postgresql+psycopg://unused/unused")
    monkeypatch.setattr(guard.socket, "gethostname", lambda: "tcou")
    monkeypatch.setattr(guard.signal, "signal", lambda *a: None)
    monkeypatch.setattr(guard, "create_engine", lambda *a, **kw: Engine())
    monkeypatch.setattr(guard, "stop_units", lambda host, armed: stopped.append((host, armed)))
    monkeypatch.setattr(sys, "argv", ["guard", "--run-id", str(uuid4()), "--armed", "--once"])
    assert guard.main() == 2
    assert stopped == [("tcou", True)]
