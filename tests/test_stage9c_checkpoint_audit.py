from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from bf4ps.stage9c_checkpoint_audit import inspect_checkpoint
from bf4ps.stage9c_supervision import CUTOVER_AT, BOUNDARY_EVENT_ID, REVISION

START = datetime(2026, 10, 8, 4, 0, tzinfo=timezone.utc)


class Result:
    def __init__(self, value):
        self.value = value

    def one(self):
        return self.value

    def one_or_none(self):
        return self.value

    def scalar_one(self):
        return self.value

    def mappings(self):
        return self

    def all(self):
        return self.value


class FakeConn:
    def __init__(self, *, readonly="on", revision=REVISION, events=None, run=True):
        self.readonly = readonly
        self.revision = revision
        self.events = events if events is not None else []
        self.has_run = run

    def execute(self, query, params=None):
        sql = str(query)
        if "current_database()" in sql:
            return Result(("bf4_playerstats_test", self.revision, False, self.readonly))
        if "FROM stage9c_supervision_runs" in sql:
            if not self.has_run:
                return Result(None)
            return Result({"state": "active",
                           "cutover_at": datetime.fromisoformat(CUTOVER_AT),
                           "since_event_id": BOUNDARY_EVENT_ID,
                           "started_at": START,
                           "deadline_at": START + timedelta(hours=6)})
        if "transaction_timestamp()" in sql:
            return Result(START + timedelta(minutes=2))
        if "FROM collection_events" in sql:
            return Result(self.events)
        raise AssertionError(f"unexpected SQL: {sql}")


def test_readonly_observed_1297_is_rejected():
    events = [{"event_id": i, "occurred_at": START - timedelta(minutes=1)}
              for i in range(1296)]
    events.append({"event_id": 1296, "occurred_at": START})
    result = inspect_checkpoint(FakeConn(events=events), uuid4())
    assert result["rolling_max"] == 1297
    assert result["observed_budget_pass"] is False
    assert result["ledger_completeness_verified"] is False


def test_observed_pass_never_certifies_completeness():
    result = inspect_checkpoint(FakeConn(), uuid4())
    assert result["observed_budget_pass"] is True
    assert result["ledger_completeness_verified"] is False


@pytest.mark.parametrize("kwargs", [
    {"readonly": "off"}, {"revision": "0003_request_gates"}, {"run": False}
])
def test_fail_closed(kwargs):
    with pytest.raises(RuntimeError):
        inspect_checkpoint(FakeConn(**kwargs), uuid4())
