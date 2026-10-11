"""Offline contract for parameterized retry fairness SQL."""
from datetime import datetime, timezone

from bf4ps.distributed_retry_metrics import RETRY_FAIRNESS_SQL


def test_query_is_read_only_and_parameterized():
    sql = str(RETRY_FAIRNESS_SQL)
    assert "FROM collection_jobs" in sql
    assert ":observed_at" in sql
    assert "INSERT " not in sql
    assert "UPDATE " not in sql
    assert "DELETE " not in sql


def test_query_separates_fresh_ready_and_deferred_retry():
    sql = str(RETRY_FAIRNESS_SQL)
    assert "fresh_eligible" in sql
    assert "retries_eligible" in sql
    assert "retries_waiting" in sql
    assert "last_error_at IS NULL" in sql
    assert "last_error_at IS NOT NULL" in sql
    assert "eligible_at > :observed_at" in sql


def test_query_reports_oldest_retry_age_by_priority_class():
    sql = str(RETRY_FAIRNESS_SQL)
    assert "oldest_retry_wait_seconds" in sql
    assert "oldest_eligible_retry_at" in sql
    assert "GROUP BY lane, resource, priority_class" in sql
