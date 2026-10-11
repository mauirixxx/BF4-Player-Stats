"""Offline three-site worker preflight contract; no database required."""
import pytest
from scripts.phase5b_three_site_worker import WorkerConfig


@pytest.mark.parametrize("host,count", [
    ("tcou", 3), ("kah-01", 3), ("hnl-01", 2),
    ("tcou", 1), ("kah-01", 16), ("hnl-01", 32),
])
def test_configured_workers_have_stable_unique_identities(host, count):
    configs = [WorkerConfig.build(host=host, worker_index=i,
                                  workers_on_host=count, run_id="test_20261010")
               for i in range(count)]
    assert len({c.collector_uuid for c in configs}) == count
    assert configs[0].collector_uuid == WorkerConfig.build(
        host=host, worker_index=0, workers_on_host=count,
        run_id="test_20261010").collector_uuid
    assert all(c.report()["http_requests"] == 0 for c in configs)
    assert all(c.report()["database_writes"] == 0 for c in configs)


def test_across_sites_identities_are_distinct():
    identities = {
        WorkerConfig.build(host=host, worker_index=i,
                           workers_on_host=n, run_id="three_sites").collector_uuid
        for host, n in (("tcou", 3), ("kah-01", 3), ("hnl-01", 2))
        for i in range(n)
    }
    assert len(identities) == 8


@pytest.mark.parametrize("kwargs", [
    {"host": "production", "worker_index": 0, "workers_on_host": 1, "run_id": "x"},
    {"host": "tcou", "worker_index": 2, "workers_on_host": 2, "run_id": "x"},
    {"host": "tcou", "worker_index": -1, "workers_on_host": 2, "run_id": "x"},
    {"host": "tcou", "worker_index": 0, "workers_on_host": 0, "run_id": "x"},
    {"host": "tcou", "worker_index": 0, "workers_on_host": 33, "run_id": "x"},
    {"host": "tcou", "worker_index": 0, "workers_on_host": 1, "run_id": "../escape"},
])
def test_reject_invalid_configuration(kwargs):
    with pytest.raises(ValueError):
        WorkerConfig.build(**kwargs)
