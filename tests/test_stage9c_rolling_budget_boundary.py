"""Offline regression tests for the Stage 9C cross-boundary rolling-hour policy.

These tests make no database or network connections. They intentionally
demonstrate why the post-boundary-only counter is insufficient.
"""
from datetime import datetime, timedelta, timezone

from bf4ps.production_hosts import RESOURCES

CEILING = 1296
T0 = datetime(2026, 10, 8, 0, 47, 34, tzinfo=timezone.utc)


def rolling_max(stamps):
    ordered = sorted(stamps)
    left = 0
    peak = 0
    for right, stamp in enumerate(ordered):
        while left <= right and ordered[left] <= stamp - timedelta(hours=1):
            left += 1
        peak = max(peak, right - left + 1)
    return peak


def eligible(event):
    return (
        event["event_type"] == "collection_attempt_started"
        and event["lane"] == "background"
        and event["resource"] in RESOURCES
    )


def budget_peak(events):
    return rolling_max(e["occurred_at"] for e in events if eligible(e))


def make_event(stamp, *, event_id, lane="background", resource="detailed",
               event_type="collection_attempt_started"):
    return dict(occurred_at=stamp, event_id=event_id, lane=lane,
                resource=resource, event_type=event_type)


def test_cross_boundary_1297_rejected_even_if_post_boundary_only_one():
    events = [make_event(T0 - timedelta(seconds=1), event_id=i)
              for i in range(1, 1297)]
    events.append(make_event(T0 + timedelta(seconds=1), event_id=11559))
    assert budget_peak(events) == 1297
    assert budget_peak(e for e in events if e["event_id"] > 11558) == 1
    assert budget_peak(events) > CEILING


def test_cross_boundary_1296_allowed():
    events = [make_event(T0 - timedelta(seconds=1), event_id=i)
              for i in range(1, 1296)]
    events.append(make_event(T0 + timedelta(seconds=1), event_id=11559))
    assert budget_peak(events) == CEILING


def test_exact_hour_cutoff_excludes_earlier_start():
    assert rolling_max([T0, T0 + timedelta(hours=1)]) == 1
    assert rolling_max([T0, T0 + timedelta(hours=1) - timedelta(microseconds=1)]) == 2


def test_interactive_terminal_and_unknown_resource_excluded():
    events = [
        make_event(T0, event_id=1),
        make_event(T0, event_id=2, lane="interactive"),
        make_event(T0, event_id=3, event_type="collection_success"),
        make_event(T0, event_id=4, resource="unsupported"),
    ]
    assert budget_peak(events) == 1


def test_timestamp_order_overrides_event_id_order():
    events = [
        make_event(T0 + timedelta(hours=2), event_id=1),
        make_event(T0, event_id=3),
        make_event(T0 + timedelta(seconds=1), event_id=2),
    ]
    assert budget_peak(events) == 2


def test_watchdog_budget_query_includes_pre_boundary_and_rejects_1297():
    from scripts.phase5b_stage9c_watchdog import rolling_background_max

    class Result:
        def mappings(self):
            return self

        def all(self):
            return self.rows

    class Connection:
        def execute(self, statement, params):
            sql = str(statement)
            assert "event_id >" not in sql
            assert "lane = 'background'" in sql
            assert "event_type = 'collection_attempt_started'" in sql
            assert params["lookback"] == T0 - timedelta(hours=1)
            assert params["now"] == T0 + timedelta(seconds=2)
            assert set(params["resources"]) == set(RESOURCES)
            result = Result()
            result.rows = [
                {"event_id": i, "occurred_at": T0 - timedelta(seconds=1)}
                for i in range(1, 1297)
            ] + [{"event_id": 11559, "occurred_at": T0 + timedelta(seconds=1)}]
            return result

    peak = rolling_background_max(
        Connection(), cutover=T0, now=T0 + timedelta(seconds=2)
    )
    assert peak == 1297
    assert peak > CEILING


def test_watchdog_budget_does_not_flag_only_pre_cutover_peak():
    from scripts.phase5b_stage9c_watchdog import rolling_background_max

    class Result:
        def mappings(self):
            return self

        def all(self):
            return [
                {"event_id": i, "occurred_at": T0 - timedelta(minutes=50)}
                for i in range(1297)
            ] + [{"event_id": 11559, "occurred_at": T0 + timedelta(minutes=20)}]

    class Connection:
        def execute(self, statement, params):
            return Result()

    # The pre-cutover 1297 starts are older than one hour at the first
    # post-cutover start. Their historic peak must not be attributed to 9C.
    assert rolling_background_max(
        Connection(), cutover=T0, now=T0 + timedelta(minutes=21)
    ) == 1


def test_watchdog_budget_query_failure_propagates_fail_closed():
    import pytest
    from scripts.phase5b_stage9c_watchdog import rolling_background_max

    class Connection:
        def execute(self, statement, params):
            raise RuntimeError("simulated database read failure")

    with pytest.raises(RuntimeError, match="database read failure"):
        rolling_background_max(Connection(), cutover=T0, now=T0 + timedelta(seconds=1))
