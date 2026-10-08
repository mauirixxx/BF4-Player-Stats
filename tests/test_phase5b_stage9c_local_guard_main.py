"""Dummy-only host-local guard main() tests; systemctl is always mocked."""
import sys
from unittest.mock import Mock
from uuid import UUID

import pytest

import scripts.phase5b_stage9c_local_guard as guard


RUN = "00000000-0000-0000-0000-000000000001"


class Engine:
    def __init__(self):
        self.disposed = False
    def connect(self):
        class Context:
            def __enter__(self):
                return object()
            def __exit__(self, *_):
                return False
        return Context()
    def dispose(self):
        self.disposed = True


def prepare(monkeypatch, *, host="tcou", armed=True, failure=None):
    engine = Engine()
    monkeypatch.setattr(sys, "argv", ["local_guard", "--run-id", RUN, "--once"] +
                        (["--armed"] if armed else []))
    monkeypatch.setattr(guard, "STOP", False)
    monkeypatch.setattr(guard.socket, "gethostname", lambda: host)
    monkeypatch.setattr(guard.signal, "signal", lambda *_: None)
    monkeypatch.setattr(guard, "database_url", lambda: "unused-test-url")
    monkeypatch.setattr(guard, "create_engine", lambda *a, **kw: engine)
    check = Mock(side_effect=failure)
    monkeypatch.setattr(guard, "check_db", check)
    runner = Mock()
    original_stop_units = guard.stop_units
    monkeypatch.setattr(guard, "stop_units", lambda host, *, armed: original_stop_units(host, armed=armed, runner=runner))
    return engine, check, runner


def test_healthy_guard_does_not_stop_anything(monkeypatch):
    engine, check, runner = prepare(monkeypatch)
    assert guard.main() == 0
    check.assert_called_once()
    assert check.call_args.args[2] == UUID(RUN)
    runner.assert_not_called()
    assert engine.disposed


@pytest.mark.parametrize("host,expected", [
    ("tcou", [guard.COLLECTOR_UNIT, guard.MATERIALIZER_UNIT]),
    ("hnl-01", [guard.COLLECTOR_UNIT]),
    ("kah-01", [guard.COLLECTOR_UNIT]),
])
def test_armed_guard_stops_exact_allowlisted_units_on_db_failure(monkeypatch, host, expected):
    engine, _, runner = prepare(monkeypatch, host=host,
                                 failure=RuntimeError("injected lease or DB failure"))
    assert guard.main() == 2
    assert [c.args[0][-1] for c in runner.call_args_list] == expected
    assert all(c.kwargs["check"] is True for c in runner.call_args_list)
    assert engine.disposed


def test_unarmed_guard_reports_failure_without_systemctl(monkeypatch):
    engine, _, runner = prepare(monkeypatch, armed=False,
                                 failure=RuntimeError("injected DB loss"))
    assert guard.main() == 2
    runner.assert_not_called()
    assert engine.disposed


def test_systemctl_failure_exits_unhealthy(monkeypatch):
    engine, _, runner = prepare(monkeypatch, failure=RuntimeError("injected lease expiry"))
    runner.side_effect = RuntimeError("injected systemctl failure")
    assert guard.main() == 2
    runner.assert_called_once()
    assert engine.disposed


def test_unsupported_host_rejected_before_connection(monkeypatch):
    engine, _, runner = prepare(monkeypatch, host="mak-01")
    create = Mock()
    monkeypatch.setattr(guard, "create_engine", create)
    with pytest.raises(SystemExit) as exc:
        guard.main()
    assert exc.value.code == 2
    create.assert_not_called()
    runner.assert_not_called()
