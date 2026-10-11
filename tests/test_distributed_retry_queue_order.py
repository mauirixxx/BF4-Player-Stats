"""Offline SQL ordering contract for best-effort failed job requeue."""
from pathlib import Path


def test_retries_follow_fresh_work_within_priority_class():
    sql = (Path(__file__).resolve().parents[1] / "bf4ps" / "collection_jobs.py").read_text()
    ordering = sql.split("ORDER BY\n                    CASE priority_class", 1)[1].split("FOR UPDATE SKIP LOCKED", 1)[0]
    assert ordering.index("END DESC") < ordering.index("CASE WHEN last_error_at IS NULL THEN 0 ELSE 1 END ASC")
    assert ordering.index("CASE WHEN last_error_at IS NULL THEN 0 ELSE 1 END ASC") < ordering.index("priority_value DESC")
    assert ordering.index("priority_value DESC") < ordering.index("eligible_at ASC")


def test_retry_still_requires_future_eligibility():
    sql = (Path(__file__).resolve().parents[1] / "bf4ps" / "collection_jobs.py").read_text()
    assert "AND eligible_at <= now()" in sql
    assert "FOR UPDATE SKIP LOCKED" in sql
