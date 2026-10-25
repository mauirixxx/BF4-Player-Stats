"""Regression: excluded soldiers must be filtered before a queue claim."""
from uuid import uuid4
from bf4ps.collection_jobs import claim_next_job

def test_claim_query_excludes_moderated_soldiers():
    class Result:
        def one_or_none(self):
            return None
    class Connection:
        def execute(self, sql, params):
            query = str(sql)
            assert "FROM collection_jobs AS queued_job" in query
            assert "JOIN player_exclusions AS excluded" in query
            assert "excluded.active" in query
            assert "soldier.soldier_id = queued_job.soldier_id" in query
            return Result()
    assert claim_next_job(Connection(), collector_uuid=uuid4()) is None
