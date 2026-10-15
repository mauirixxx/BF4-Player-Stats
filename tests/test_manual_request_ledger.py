from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import pytest
from bf4ps.manual_request_ledger import accept_existing_soldier_request

NOW = datetime(2026, 10, 15, tzinfo=timezone.utc)

class FakeConnection:
    def __init__(self, *, exists=True, last_accepted_at=None):
        self.exists = exists
        self.last_accepted_at = last_accepted_at
        self.sql = []

    def execute(self, statement, params=None):
        sql = str(statement)
        self.sql.append(sql)
        if 'FROM soldiers' in sql:
            return SimpleNamespace(scalar_one_or_none=lambda: 42 if self.exists else None)
        if 'clock_timestamp()' in sql:
            return SimpleNamespace(scalar_one=lambda: NOW)
        if 'FROM manual_request_cooldowns' in sql:
            return SimpleNamespace(one_or_none=lambda: SimpleNamespace(last_accepted_at=self.last_accepted_at, last_request_id=99) if self.last_accepted_at else None)
        if 'INSERT INTO manual_collection_requests' in sql:
            return SimpleNamespace(scalar_one=lambda: 100)
        return SimpleNamespace()


def test_acceptance_locks_soldier_before_reading_cooldown():
    c = FakeConnection()
    result = accept_existing_soldier_request(c, soldier_id=42, kind='refresh')
    assert result.accepted and result.request_id == 100
    assert 'FOR UPDATE' in c.sql[0]
    assert 'FROM manual_request_cooldowns' in c.sql[2]
    assert 'INSERT INTO manual_request_cooldowns' in c.sql[-1]


def test_cooldown_returns_original_request_without_inserting():
    c = FakeConnection(last_accepted_at=NOW-timedelta(minutes=10))
    result = accept_existing_soldier_request(c, soldier_id=42, kind='refresh')
    assert result.retry_after_seconds == 3000 and result.request_id == 99
    assert not result.accepted
    assert not any('INSERT INTO' in q for q in c.sql)


def test_expired_cooldown_accepts():
    c = FakeConnection(last_accepted_at=NOW-timedelta(hours=2))
    assert accept_existing_soldier_request(c, soldier_id=42, kind='add').accepted


def test_missing_soldier_rejected_without_insert():
    c = FakeConnection(exists=False)
    with pytest.raises(ValueError, match='not registered'):
        accept_existing_soldier_request(c, soldier_id=42, kind='add')
    assert len(c.sql) == 1

@pytest.mark.parametrize('soldier_id,kind', [(0,'add'),(-1,'refresh'),(True,'add'),(1,'admin')])
def test_invalid_input(soldier_id, kind):
    with pytest.raises(ValueError):
        accept_existing_soldier_request(FakeConnection(), soldier_id=soldier_id, kind=kind)