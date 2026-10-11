"""Offline recovery-path tests using a deterministic fake SQL connection.

No PostgreSQL writes, external requests, or collector activation.
"""
from dataclasses import dataclass
from unittest.mock import Mock

import pytest

from scripts.phase5b_three_site_manifest import RunManifest
from scripts.phase5b_three_site_recovery import recover_state


@dataclass
class Row:
    soldier_id: int = 0
    job_id: int = 0
    reason: str = ""
    collector_uuid: str = ""
    collector_name: str = ""


class Result:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return self.rows


class Connection:
    def __init__(self, soldiers, jobs=(), collectors=()):
        self.results = [soldiers, jobs, collectors]
        self.calls = []

    def execute(self, statement, parameters):
        self.calls.append((str(statement), parameters))
        return Result(self.results.pop(0))


def manifest():
    return RunManifest.build(
        run_id="recover_test", distribution={"tcou": 1, "kah-01": 1},
        job_count=2)


def make_connection(m):
    prefix = "synthetic-three-site-recover_test-"
    workers = m.payload()["collector_uuids"]
    return Connection(
        [101, 102],
        [Row(soldier_id=101, job_id=201, reason=prefix + "0"),
         Row(soldier_id=102, job_id=202, reason=prefix + "1")],
        [Row(collector_uuid=worker, collector_name=prefix + worker)
         for worker in workers],
    )


def test_recover_exact_committed_cohort():
    m = manifest()
    conn = make_connection(m)
    state = recover_state(conn, m)
    assert state["soldier_ids"] == [101, 102]
    assert state["job_ids"] == [201, 202]
    assert state["manifest_sha256"] == m.report()["sha256"]
    assert len(conn.calls) == 3
    assert all("synthetic-three-site-recover_test-%" in str(p)
               for _, params in conn.calls for p in params.values()
               if isinstance(p, str) and p.startswith("synthetic-three-site"))


def test_no_committed_cohort():
    assert recover_state(Connection([]), manifest()) is None


def test_partial_soldiers_rejected():
    with pytest.raises(RuntimeError, match="partial"):
        recover_state(Connection([101]), manifest())


def test_wrong_job_reason_rejected():
    m = manifest()
    conn = make_connection(m)
    conn.results[1][0].reason = "not-our-job"
    with pytest.raises(RuntimeError, match="jobs"):
        recover_state(conn, m)


def test_wrong_collector_rejected():
    m = manifest()
    conn = make_connection(m)
    conn.results[2][0].collector_name = "unexpected"
    with pytest.raises(RuntimeError, match="collectors"):
        recover_state(conn, m)


def test_missing_job_rejected():
    m = manifest()
    conn = make_connection(m)
    conn.results[1].pop()
    with pytest.raises(RuntimeError, match="jobs"):
        recover_state(conn, m)
