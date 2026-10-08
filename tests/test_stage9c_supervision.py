"""Offline safety tests: no PostgreSQL, systemd or Battlelog calls."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from bf4ps.stage9c_supervision import (
    ABORT_SQL, RENEW_SQL, BOUNDARY_EVENT_ID, CUTOVER_AT,
    SupervisionRefused, abort_owned_run, renew_after_inspection,
    require_guard_lease,
)


class Result:
    def __init__(self, row):
        self.row = row

    def one_or_none(self):
        return self.row

    def mappings(self):
        return self


class Conn:
    def __init__(self, row):
        self.row = row
        self.calls = []

    def execute(self, statement, params):
        self.calls.append((str(statement), params))
        return Result(self.row)


def active_row():
    now = datetime.now(timezone.utc)
    return {
        "state": "active",
        "cutover_at": datetime.fromisoformat(CUTOVER_AT),
        "since_event_id": BOUNDARY_EVENT_ID,
        "started_at": now - timedelta(hours=1),
        "deadline_at": now + timedelta(hours=5),
        "watchdog_owner": uuid4(),
        "watchdog_generation": 1,
        "heartbeat_at": now - timedelta(seconds=2),
        "lease_expires_at": now + timedelta(seconds=18),
        "db_now": now,
    }


def test_guard_accepts_fresh_matching_run():
    row = active_row()
    assert require_guard_lease(Conn(row), uuid4()) is row


@pytest.mark.parametrize("change", [
    {"state": "aborted"}, {"state": "completed"}, {"state": "prepared"},
    {"since_event_id": BOUNDARY_EVENT_ID + 1},
    {"watchdog_owner": None}, {"watchdog_generation": 0},
    {"heartbeat_at": None}, {"lease_expires_at": None},
])
def test_guard_rejects_invalid_run(change):
    row = {**active_row(), **change}
    with pytest.raises(SupervisionRefused):
        require_guard_lease(Conn(row), uuid4())


def test_guard_rejects_expiry_and_deadline():
    for key in ("lease_expires_at", "deadline_at"):
        row = active_row()
        row[key] = row["db_now"]
        with pytest.raises(SupervisionRefused):
            require_guard_lease(Conn(row), uuid4())


def test_guard_rejects_missing_run():
    with pytest.raises(SupervisionRefused):
        require_guard_lease(Conn(None), uuid4())


def test_failed_inspection_never_issues_sql():
    conn = Conn(None)
    with pytest.raises(SupervisionRefused):
        renew_after_inspection(conn, run_id=uuid4(), owner=uuid4(),
                               generation=1, inspection_passed=False)
    assert not conn.calls


def test_renew_fenced_and_expiry_conditions():
    sql = str(RENEW_SQL)
    assert "watchdog_owner=:owner" in sql
    assert "watchdog_generation=:generation" in sql
    assert "lease_expires_at > clock_timestamp()" in sql
    assert "deadline_at > clock_timestamp()" in sql
    assert "state='active'" in sql
    with pytest.raises(SupervisionRefused):
        renew_after_inspection(Conn(None), run_id=uuid4(), owner=uuid4(),
                               generation=1, inspection_passed=True)


def test_abort_requires_owner_and_is_sticky():
    sql = str(ABORT_SQL)
    assert "state='active'" in sql
    assert "watchdog_owner=:owner" in sql
    assert "watchdog_generation=:generation" in sql
    assert "state='aborted'" in sql
    with pytest.raises(SupervisionRefused):
        abort_owned_run(Conn(None), run_id=uuid4(), owner=uuid4(),
                        generation=1, reason="http 429")


def test_abort_requires_reason_and_valid_generation():
    with pytest.raises(ValueError):
        abort_owned_run(Conn(None), run_id=uuid4(), owner=uuid4(),
                        generation=1, reason=" ")
    with pytest.raises(SupervisionRefused):
        renew_after_inspection(Conn(None), run_id=uuid4(), owner=uuid4(),
                               generation=0, inspection_passed=True)
