"""No-network entrypoint contract tests: never start services or connect to PostgreSQL."""
import sys
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import scripts.phase5b_stage9c_watchdog as watchdog
from bf4ps.stage9c_supervision import CUTOVER_AT, BOUNDARY_EVENT_ID


RUN = "00000000-0000-0000-0000-000000000001"
OWNER = "00000000-0000-0000-0000-000000000002"


def argv(*extra):
    return ["watchdog", "--run-id", RUN, "--watchdog-owner", OWNER,
            "--watchdog-generation", "1", "--cutover-at", CUTOVER_AT,
            "--since-event-id", str(BOUNDARY_EVENT_ID), "--once", *extra]


class FakeEngine:
    def __init__(self):
        self.conn = object()
        self.disposed = False
        self.commits = 0
        self.rollbacks = 0
    def begin(self):
        engine = self
        class Context:
            def __enter__(self):
                return engine.conn
            def __exit__(self, exc_type, *_):
                if exc_type is None:
                    engine.commits += 1
                else:
                    engine.rollbacks += 1
                return False
        return Context()
    def dispose(self):
        self.disposed = True


def setup(monkeypatch, *, args=None, started=None, issues=None, fail_inspect=False):
    engine = FakeEngine()
    monkeypatch.setattr(sys, "argv", args or argv())
    monkeypatch.setattr(watchdog, "STOP", False)
    monkeypatch.setattr(watchdog.signal, "signal", lambda *_: None)
    monkeypatch.setattr(watchdog, "database_url", lambda: "unused-test-url")
    monkeypatch.setattr(watchdog, "create_engine", lambda *a, **kw: engine)
    validate = Mock()
    monkeypatch.setattr(watchdog, "validate_target", validate)
    started = started or datetime(2026, 10, 8, 1, 15, tzinfo=timezone.utc)
    lease = Mock(return_value={"started_at": started})
    monkeypatch.setattr(watchdog, "require_guard_lease", lease)
    inspect = Mock(return_value=(issues or [], 0, 0, 0))
    if fail_inspect:
        inspect.side_effect = RuntimeError("injected database failure")
    monkeypatch.setattr(watchdog, "inspect", inspect)
    renew = Mock()
    abort = Mock()
    drain = Mock(return_value=3)
    monkeypatch.setattr(watchdog, "renew_after_inspection", renew)
    monkeypatch.setattr(watchdog, "abort_owned_run", abort)
    monkeypatch.setattr(watchdog, "drain_fleet", drain)
    return SimpleNamespace(engine=engine, lease=lease, inspect=inspect,
                           renew=renew, abort=abort, drain=drain, started=started)


def test_armed_main_uses_persisted_supervision_start(monkeypatch):
    f = setup(monkeypatch, args=argv("--armed"))
    assert watchdog.main() == 0
    assert f.inspect.call_args.kwargs["supervision_start"] == f.started
    f.renew.assert_called_once()
    f.abort.assert_not_called()
    f.drain.assert_not_called()
    assert f.engine.disposed


def test_unarmed_main_does_not_mutate(monkeypatch):
    f = setup(monkeypatch, issues=["injected throttle"])
    assert watchdog.main() == 2
    f.renew.assert_not_called()
    f.abort.assert_not_called()
    f.drain.assert_not_called()


def test_armed_main_commits_abort_and_drain_on_issue(monkeypatch):
    f = setup(monkeypatch, args=argv("--armed"), issues=["injected throttle"])
    assert watchdog.main() == 2
    f.abort.assert_called_once()
    f.drain.assert_called_once()
    f.renew.assert_not_called()


def test_database_failure_fails_closed_without_renewal(monkeypatch):
    f = setup(monkeypatch, args=argv("--armed"), fail_inspect=True)
    assert watchdog.main() == 3
    f.renew.assert_not_called()
    f.abort.assert_not_called()
    f.drain.assert_not_called()
    assert f.engine.disposed


def test_expired_lease_fails_closed(monkeypatch):
    f = setup(monkeypatch, args=argv("--armed"))
    f.lease.side_effect = RuntimeError("lease expired")
    assert watchdog.main() == 3
    f.inspect.assert_not_called()
    f.renew.assert_not_called()
    f.abort.assert_not_called()
    f.drain.assert_not_called()


@pytest.mark.parametrize("extra", [
    ("--since-event-id", str(BOUNDARY_EVENT_ID + 1)),
    ("--watchdog-generation", "0"),
    ("--interval-seconds", "6"),
    ("--inflight-grace-seconds", "59"),
])
def test_invalid_cli_rejected_before_db_connection(monkeypatch, extra):
    monkeypatch.setattr(sys, "argv", argv(*extra))
    create = Mock()
    monkeypatch.setattr(watchdog, "create_engine", create)
    with pytest.raises(SystemExit) as exc:
        watchdog.main()
    assert exc.value.code == 2
    create.assert_not_called()


def test_atomic_drain_failure_rolls_back_then_fallback_aborts(monkeypatch):
    f = setup(monkeypatch, args=argv("--armed"), issues=["injected throttle"])
    f.drain.side_effect = RuntimeError("injected fleet drift")
    assert watchdog.main() == 2
    assert f.engine.rollbacks == 1
    assert f.engine.commits == 1
    assert f.abort.call_count == 2
    assert "fleet drain failed" in f.abort.call_args.kwargs["reason"]
    f.renew.assert_not_called()


def test_failed_fallback_does_not_claim_success(monkeypatch):
    f = setup(monkeypatch, args=argv("--armed"), issues=["injected throttle"])
    f.drain.side_effect = RuntimeError("injected fleet drift")
    f.abort.side_effect = [None, RuntimeError("injected fenced abort rejection")]
    assert watchdog.main() == 3
    assert f.engine.rollbacks == 2
    assert f.engine.commits == 0
    f.renew.assert_not_called()


def test_atomic_abort_failure_never_drains_or_renews(monkeypatch):
    f = setup(monkeypatch, args=argv("--armed"), issues=["injected throttle"])
    f.abort.side_effect = RuntimeError("injected abort failure")
    assert watchdog.main() == 3
    assert f.engine.rollbacks == 1
    assert f.engine.commits == 0
    f.drain.assert_not_called()
    f.renew.assert_not_called()


def test_renewal_failure_rolls_back_and_exits(monkeypatch):
    f = setup(monkeypatch, args=argv("--armed"))
    f.renew.side_effect = RuntimeError("injected renewal failure")
    assert watchdog.main() == 3
    assert f.engine.rollbacks == 1
    assert f.engine.commits == 0
    f.abort.assert_not_called()
    f.drain.assert_not_called()


def test_successful_armed_abort_commits_atomically(monkeypatch):
    f = setup(monkeypatch, args=argv("--armed"), issues=["injected throttle"])
    assert watchdog.main() == 2
    assert f.engine.commits == 1
    assert f.engine.rollbacks == 0
    f.abort.assert_called_once()
    f.drain.assert_called_once()


@pytest.mark.parametrize("bad_start", [None, "not-a-timestamp", datetime(2026, 10, 8, 1, 15)])
def test_invalid_supervision_start_fails_closed(monkeypatch, bad_start):
    f = setup(monkeypatch, args=argv("--armed"))
    f.lease.return_value = {"started_at": bad_start}
    assert watchdog.main() == 3
    f.inspect.assert_not_called()
    f.renew.assert_not_called()
    f.abort.assert_not_called()
    f.drain.assert_not_called()
    assert f.engine.rollbacks == 1
