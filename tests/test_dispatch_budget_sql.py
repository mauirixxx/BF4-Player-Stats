"""Static offline checks for D2 SQL accounting boundaries."""
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from bf4ps.dispatch_budget_sql import USAGE_SQL, read_conservative_background_usage


def test_query_is_read_only_and_uses_three_sources():
    sql = str(USAGE_SQL).lower()
    for table in ("collection_events", "collection_jobs", "outbound_dispatches"):
        assert table in sql
    assert "union all" in sql
    assert "lease_expires_at > :at" in sql
    assert "greatest(starts - 1, 0)" in sql
    for forbidden in ("insert ", "update ", "delete ", "truncate ", "pg_advisory_xact_lock"):
        assert forbidden not in sql


def test_query_requires_aware_clock():
    with pytest.raises(ValueError, match="timezone-aware"):
        read_conservative_background_usage(Mock(), at=datetime(2026, 10, 10))


def test_query_uses_single_supplied_timestamp():
    conn = Mock()
    conn.execute.return_value.scalar_one.return_value = 12
    at = datetime(2026, 10, 10, tzinfo=timezone.utc)
    assert read_conservative_background_usage(conn, at=at) == 12
    assert conn.execute.call_args.args[0] is USAGE_SQL
    assert conn.execute.call_args.args[1] == {"at": at}
