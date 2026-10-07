from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from bf4ps.production_hosts import HOSTS, LEASE_SECONDS, REQUEST_INTERVAL_SECONDS, RESOURCES

P = Path("scripts/bf4ps_production_collector.py")


def _source() -> str:
    return P.read_text()


def _module():
    spec = importlib.util.spec_from_file_location("bf4ps_production_collector", P)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_production_collector_parses_and_imports():
    ast.parse(_source())
    _module()


def test_production_host_contract_is_stable_and_not_step_harness_owned():
    assert set(HOSTS) == {"hnl-01", "kah-01", "tcou"}
    assert len({h.collector_uuid for h in HOSTS.values()}) == 3
    assert len({h.egress_key for h in HOSTS.values()}) == 3
    assert REQUEST_INTERVAL_SECONDS == 5.0
    assert LEASE_SECONDS == 120
    assert RESOURCES == ("detailed", "weapons", "vehicles")


@pytest.mark.parametrize(
    ("resource", "function_name"),
    [
        ("detailed", "collect_one_detailed_job"),
        ("weapons", "collect_one_weapon_job"),
        ("vehicles", "collect_one_vehicle_job"),
    ],
)
def test_collect_one_passes_only_production_runtime_contract(monkeypatch, resource, function_name):
    module = _module()
    engine = object()
    identity = object()
    calls = []

    def fake_collector(received_engine, **kwargs):
        calls.append((received_engine, kwargs))
        return None

    monkeypatch.setattr(module, function_name, fake_collector)
    assert module.collect_one(engine, identity, resource) is None
    assert len(calls) == 1
    received_engine, kwargs = calls[0]
    assert received_engine is engine
    assert kwargs == {
        "identity": identity,
        "request_interval_seconds": 5.0,
        "lease_seconds": 120,
        "enforce_production_budget": True,
        "timeout_seconds": 30.0,
    }


def test_collect_one_rejects_nonproduction_resource():
    module = _module()
    with pytest.raises(ValueError, match="unsupported production resource"):
        module.collect_one(object(), object(), "profile")


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
    module = _module()
    for http_status, error_class, expected in [
        (403, "http_error", True),
        (429, "http_error", True),
        (500, "battlelog_throttle", True),
        (500, "temporary_http", False),
    ]:
        result = SimpleNamespace(
            soldier_id=1,
            job_id=2,
            platform="pc",
            http_status=http_status,
            error_class=error_class,
            retry_after_seconds=900,
            duration_ms=123,
        )
        monkeypatch_types = (module.FailedJob, module.FailedWeaponJob, module.FailedVehicleJob)
        original = module.FailedJob
        try:
            module.FailedJob = type(result)
            _, throttle = module.describe_result("detailed", result)
            assert throttle is expected
        finally:
            module.FailedJob = original
