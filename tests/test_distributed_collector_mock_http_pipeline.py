"""Execute complete collector control flow with mocked HTTP and database adapters.

No socket access, real HTTP, production database, or scratch writes.
"""
from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from uuid import UUID

import pytest

from bf4ps.collection_jobs import ClaimedJob
from bf4ps import detailed_collector, weapon_collector, vehicle_collector


class FakeEngine:
    @contextmanager
    def begin(self):
        yield object()

    @contextmanager
    def connect(self):
        yield object()


@pytest.mark.parametrize("resource,module,entry,fetch,normalize,persist,attempt,logger", [
    ("detailed", detailed_collector, "collect_one_detailed_job",
     "fetch_detailed_stats", "normalize_detailed_stats", "persist_detailed_success",
     "_record_detailed_attempt_started", "_record_detailed_persistence_failure"),
    ("weapons", weapon_collector, "collect_one_weapon_job",
     "fetch_weapon_stats", "normalize_weapon_stats", "persist_weapon_success",
     "_record_attempt_started", "_record_persistence_failure"),
    ("vehicles", vehicle_collector, "collect_one_vehicle_job",
     "fetch_vehicle_stats", "normalize_vehicle_stats", "persist_vehicle_success",
     "_record_vehicle_attempt_started", "_record_vehicle_persistence_failure"),
])
@pytest.mark.parametrize("winner_confirmed", [False, True])
def test_mock_http_collector_lease_loss_audits_or_discards(
    monkeypatch, resource, module, entry, fetch, normalize, persist,
    attempt, logger, winner_confirmed,
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
    monkeypatch.setattr(module, fetch,
                        lambda *args, **kwargs: (
                            calls.append("mock_http") or SimpleNamespace(
                                payload={}, platform_int=1, response_bytes=15
                            )
                        ))
    monkeypatch.setattr(module, normalize,
                        lambda *args, **kwargs: calls.append("normalized") or {})
    monkeypatch.setattr(module, persist,
                        lambda *args, **kwargs: (
                            calls.append("persist") or (_ for _ in ()).throw(
                                RuntimeError(
                                    resource[:-1] + " success rejected: job lease is no longer owned"
                                    if resource == "weapons" else
                                    ("vehicle" if resource == "vehicles" else "detailed")
                                    + " success rejected: job lease is no longer owned"
                                )
                            )
                        ))
    monkeypatch.setattr(module, logger,
                        lambda engine, **kwargs: calls.append(("audit_failure", kwargs["exc"])))
    # This is a pure fake of the duplicate classifier. The real PostgreSQL
    # classifier and event writer have their own guarded D2 integration tests.
    import bf4ps.distributed_duplicate_events as duplicates
    monkeypatch.setattr(duplicates, "record_discarded_duplicate",
                        lambda conn, **kwargs: calls.append("classify_duplicate") or winner_confirmed)

    if winner_confirmed:
        assert getattr(module, entry)(FakeEngine(), identity=identity,
                                      request_interval_seconds=0) is None
        assert not any(isinstance(item, tuple) and item[0] == "audit_failure"
                       for item in calls)
    else:
        with pytest.raises(RuntimeError, match="job lease is no longer owned"):
            getattr(module, entry)(FakeEngine(), identity=identity,
                                   request_interval_seconds=0)
        assert sum(isinstance(item, tuple) and item[0] == "audit_failure"
                   for item in calls) == 1
    assert calls[:4] == ["attempt", "mock_http", "normalized", "persist"]
    assert calls[4] == "classify_duplicate"
