from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

from bf4ps.production_hosts import HOSTS, REQUEST_INTERVAL_SECONDS, RESOURCES

P = Path("scripts/bf4ps_production_collector.py")


def _source() -> str:
    return P.read_text()


def test_production_collector_parses_and_imports():
    ast.parse(_source())
    spec = importlib.util.spec_from_file_location("bf4ps_production_collector", P)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)


def test_production_host_contract_is_stable_and_not_step_harness_owned():
    assert set(HOSTS) == {"hnl-01", "kah-01", "tcou"}
    assert len({h.collector_uuid for h in HOSTS.values()}) == 3
    assert len({h.egress_key for h in HOSTS.values()}) == 3
    assert REQUEST_INTERVAL_SECONDS == 5.0
    assert RESOURCES == ("detailed", "weapons", "vehicles")


def test_production_daemon_uses_production_budget_without_test_bounds():
    s = _source()
    assert "enforce_production_budget=True" in s
    assert "allowed_soldier_ids" not in s
    assert "max_total_attempts" not in s
    assert "attempts_after_event_id" not in s
    assert "GLOBAL_ATTEMPT_CEILING" not in s
    assert "phase5b_step7" not in s.lower()


def test_production_daemon_preserves_operator_controls_and_clean_stop():
    s = _source()
    assert "heartbeat_collector" in s
    assert "if not control.enabled" in s
    assert "if control.drained" in s
    assert "stop_collector" in s
    assert "signal.SIGTERM" in s
    assert "signal.SIGINT" in s


def test_production_daemon_stops_on_throttle_signals():
    s = _source()
    assert "result.http_status in {403, 429}" in s
    assert 'result.error_class == "battlelog_throttle"' in s
    assert "THROTTLE SIGNAL; stopping production collector" in s
