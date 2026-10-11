"""Full collector retry control flow with synthetic HTTP failures and no network."""
from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from uuid import UUID

import pytest

from bf4ps.collection_jobs import ClaimedJob
from bf4ps import detailed_collector, weapon_collector, vehicle_collector
from bf4ps.battlelog_detailed import DetailedStatsHTTPError, DetailedStatsTransportError
from bf4ps.battlelog_weapons import WeaponStatsHTTPError, WeaponStatsTransportError
from bf4ps.battlelog_vehicles import VehicleStatsHTTPError, VehicleStatsTransportError


class FakeEngine:
    @contextmanager
    def begin(self):
        yield object()

    @contextmanager
    def connect(self):
        yield object()


CASES = (
    ("detailed", detailed_collector, "collect_one_detailed_job", "fetch_detailed_stats",
     "_record_detailed_attempt_started", "persist_detailed_retry_failure",
     DetailedStatsHTTPError, DetailedStatsTransportError),
    ("weapons", weapon_collector, "collect_one_weapon_job", "fetch_weapon_stats",
     "_record_attempt_started", "persist_weapon_retry_failure",
     WeaponStatsHTTPError, WeaponStatsTransportError),
    ("vehicles", vehicle_collector, "collect_one_vehicle_job", "fetch_vehicle_stats",
     "_record_vehicle_attempt_started", "persist_vehicle_retry_failure",
     VehicleStatsHTTPError, VehicleStatsTransportError),
)


@pytest.mark.parametrize("resource,module,entry,fetch,attempt,persist,http_error,transport_error", CASES)
@pytest.mark.parametrize("kind,status,expected_class", (
    ("http", 403, "battlelog_throttle"),
    ("http", 429, "battlelog_throttle"),
    ("http", 503, "battlelog_http_5xx"),
    ("transport", None, "battlelog_transport"),
))
def test_collector_mock_http_failure_reschedules(
    monkeypatch, resource, module, entry, fetch, attempt, persist,
    http_error, transport_error, kind, status, expected_class,
):
    job = ClaimedJob(12, 34, resource, "background", 1, UUID(int=1), UUID(int=2))
    identity = module.CollectorIdentity(
        collector_uuid=job.collector_uuid, collector_name="mock-worker",
        hostname="tcou", egress_key="no-network",
    )
    calls = []
    monkeypatch.setattr(module, "claim_next_job", lambda conn, **kwargs: job)
    monkeypatch.setattr(module, "mark_job_running", lambda conn, claimed: True)
    monkeypatch.setattr(module, "_soldier_identity", lambda engine, sid: (123, "pc"))
    monkeypatch.setattr(module, "reserve_request_slot",
                        lambda conn, **kwargs: SimpleNamespace(wait_seconds=0))
    monkeypatch.setattr(module, attempt,
                        lambda engine, **kwargs: calls.append("attempt"))
    error = (http_error(status, f"synthetic HTTP {status}")
             if kind == "http" else transport_error("synthetic transport failure"))

    def mocked_fetch(*args, **kwargs):
        calls.append("mock_http")
        raise error

    monkeypatch.setattr(module, fetch, mocked_fetch)
    monkeypatch.setattr(module, "retry_delay_for_failure",
                        lambda conn, **kwargs: 77)

    def mocked_persist(conn, **kwargs):
        calls.append(("persist_failure", kwargs))
        assert kwargs["job"] == job
        assert kwargs["failure"].error_class == expected_class
        assert kwargs["failure"].http_status == status
        assert kwargs["retry_after_seconds"] == 77

    monkeypatch.setattr(module, persist, mocked_persist)
    result = getattr(module, entry)(FakeEngine(), identity=identity,
                                    request_interval_seconds=0)
    assert result.error_class == expected_class
    assert result.http_status == status
    assert result.retry_after_seconds == 77
    assert calls[:2] == ["attempt", "mock_http"]
    assert len(calls) == 3 and calls[2][0] == "persist_failure"


@pytest.mark.parametrize("resource,module,entry,fetch,attempt,persist,http_error,transport_error", CASES)
def test_explicit_retry_override_skips_delay_lookup(
    monkeypatch, resource, module, entry, fetch, attempt, persist,
    http_error, transport_error,
):
    job = ClaimedJob(12, 34, resource, "background", 1, UUID(int=1), UUID(int=2))
    identity = module.CollectorIdentity(UUID(int=1), "mock-worker", "tcou", "no-network")
    monkeypatch.setattr(module, "claim_next_job", lambda conn, **kwargs: job)
    monkeypatch.setattr(module, "mark_job_running", lambda conn, claimed: True)
    monkeypatch.setattr(module, "_soldier_identity", lambda engine, sid: (123, "pc"))
    monkeypatch.setattr(module, "reserve_request_slot",
                        lambda conn, **kwargs: SimpleNamespace(wait_seconds=0))
    monkeypatch.setattr(module, attempt, lambda engine, **kwargs: None)

    def mocked_fetch(*args, **kwargs):
        raise http_error(429, "synthetic throttle")

    monkeypatch.setattr(module, fetch, mocked_fetch)
    monkeypatch.setattr(module, "retry_delay_for_failure",
                        lambda *args, **kwargs: (_ for _ in ()).throw(
                            AssertionError("override should bypass retry delay lookup")))
    monkeypatch.setattr(module, persist,
                        lambda conn, **kwargs: None if kwargs["retry_after_seconds"] == 19
                        else (_ for _ in ()).throw(AssertionError("wrong retry override")))
    result = getattr(module, entry)(FakeEngine(), identity=identity,
                                    request_interval_seconds=0, retry_after_seconds=19)
    assert result.retry_after_seconds == 19
