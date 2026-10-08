"""No-network local guard behavior tests."""
from unittest.mock import Mock
import pytest

from scripts.phase5b_stage9c_local_guard import (
    COLLECTOR_UNIT, MATERIALIZER_UNIT, check_db, stop_units,
)


class Result:
    def __init__(self, value=None, row=None):
        self.value, self.row = value, row
    def scalar_one(self):
        return self.value
    def mappings(self):
        return self
    def one_or_none(self):
        return self.row


class Connection:
    def __init__(self, *, drained=False, database="bf4_playerstats_test"):
        self.drained, self.database = drained, database
    def execute(self, statement, params=None):
        sql = str(statement)
        if "current_database()" in sql:
            return Result(value=self.database)
        if "alembic_version" in sql:
            return Result(value="0003_request_gates")
        if "pg_is_in_recovery()" in sql:
            return Result(value=False)
        if "transaction_read_only" in sql:
            return Result(value="off")
        if "FROM collectors" in sql:
            return Result(row=dict(collector_name="phase3e-tcou", hostname="tcou",
                                   egress_key="phase3e-tcou", lane="background",
                                   enabled=True, drained=self.drained, retired_at=None))
        raise AssertionError(sql)


def test_local_db_healthy():
    check_db(Connection(), "tcou")


def test_local_drain_detected():
    with pytest.raises(RuntimeError, match="disabled or drained"):
        check_db(Connection(drained=True), "tcou")


def test_local_wrong_database_detected():
    with pytest.raises(RuntimeError, match="database safety mismatch"):
        check_db(Connection(database="postgres"), "tcou")


def test_dry_run_never_stops_units():
    runner = Mock()
    stop_units("tcou", armed=False, runner=runner)
    runner.assert_not_called()


def test_armed_tcou_stops_collector_and_materializer():
    runner = Mock()
    stop_units("tcou", armed=True, runner=runner)
    assert [call.args[0][-1] for call in runner.call_args_list] == [
        COLLECTOR_UNIT, MATERIALIZER_UNIT
    ]


def test_armed_remote_stops_only_collector():
    runner = Mock()
    stop_units("hnl-01", armed=True, runner=runner)
    assert [call.args[0][-1] for call in runner.call_args_list] == [COLLECTOR_UNIT]
