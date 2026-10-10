from types import SimpleNamespace
from uuid import UUID

from bf4ps.collection_jobs import ClaimedJob
from bf4ps.distributed_duplicate_events import classify_stale_result, record_discarded_duplicate

job = ClaimedJob(12, 34, "detailed", "background", 2, UUID(int=1), UUID(int=2))

class FakeConnection:
    def __init__(self, winner=None):
        self.winner = winner
        self.queries = []
        self.discarded = False
    def execute(self, statement, params):
        self.queries.append((str(statement), params))
        if "SELECT 1 FROM collection_events" in str(statement):
            return SimpleNamespace(one_or_none=lambda: (1,) if self.discarded else None)
        if "INSERT INTO collection_events" in str(statement):
            self.discarded = True
        if "SELECT event_id" in str(statement):
            return SimpleNamespace(one_or_none=lambda: None if self.winner is None else (self.winner,))
        return SimpleNamespace(rowcount=1)

def kwargs():
    return dict(job=job, persona_id=123, platform="pc", collector_name="worker", hostname="tcou", egress_key="egress", duration_ms=100, http_status=200)

def test_stale_without_success_is_not_duplicate():
    conn = FakeConnection()
    assert not record_discarded_duplicate(conn, **kwargs())
    assert len(conn.queries) == 3

def test_confirmed_winner_is_logged():
    conn = FakeConnection(42)
    assert record_discarded_duplicate(conn, **kwargs())
    assert "collection_duplicate_discarded" in conn.queries[-1][0]
    assert conn.queries[-1][1]["winner_event_id"] == 42

def test_classification_scopes_job_and_resource():
    conn = FakeConnection(42)
    assert classify_stale_result(conn, job=job).duplicate
    assert "resource = :resource" in conn.queries[0][0]


def test_repeat_duplicate_discard_is_idempotent():
    conn = FakeConnection(42)
    assert record_discarded_duplicate(conn, **kwargs())
    assert not record_discarded_duplicate(conn, **kwargs())
    assert sum("INSERT INTO collection_events" in sql for sql, _ in conn.queries) == 1


def test_duplicate_event_lock_is_scoped_to_attempt():
    conn = FakeConnection(42)
    assert record_discarded_duplicate(conn, **kwargs())
    assert "pg_advisory_xact_lock" in conn.queries[0][0]
    assert conn.queries[0][1]["attempt_identity"] == f"{job.job_id}:{job.attempt_count}:{job.lease_token}"
