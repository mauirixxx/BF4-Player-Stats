"""Schema-aligned read-only distributed collection metrics contract."""
from bf4ps.distributed_collection_metrics import DUPLICATE_AND_FAILURE_COUNTS_SQL


def test_uses_documented_collection_events_table():
    sql = str(DUPLICATE_AND_FAILURE_COUNTS_SQL)
    assert "FROM collection_events" in sql
    assert "collection_duplicate_discarded" in sql
    assert "collection_failure" in sql
    assert "collection_success" in sql


def test_metrics_split_by_host_egress_resource_and_hour():
    sql = str(DUPLICATE_AND_FAILURE_COUNTS_SQL)
    for field in ("hostname_snapshot", "egress_key_snapshot", "resource", "date_trunc('hour', occurred_at)"):
        assert field in sql


def test_throttle_failures_separate_from_other_failures():
    assert "http_status IN (403, 429)" in str(DUPLICATE_AND_FAILURE_COUNTS_SQL)


def test_read_only_parameterized_bounded_query():
    sql = str(DUPLICATE_AND_FAILURE_COUNTS_SQL).upper()
    assert ":SINCE" in sql and ":UNTIL" in sql
    for forbidden in ("INSERT ", "UPDATE ", "DELETE ", "ALTER ", "DROP "):
        assert forbidden not in sql
