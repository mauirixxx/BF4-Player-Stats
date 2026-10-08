"""Offline Stage 9C supervision-anchor regressions; no DB/network."""
from datetime import datetime, timedelta, timezone

from scripts.phase5b_stage9c_watchdog import rolling_background_max

T0 = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def all(self):
        return self.rows


class FakeConnection:
    def __init__(self, stamps):
        self.stamps = stamps
        self.params = None

    def execute(self, statement, params):
        self.params = params
        eligible = [
            t for t in self.stamps
            if params["lookback"] < t <= params["now"]
        ]
        return Rows([
            {"event_id": i, "occurred_at": t}
            for i, t in enumerate(sorted(eligible))
        ])


def test_trial_start_not_frozen_materialization_cutover():
    conn = FakeConnection([T0 - timedelta(days=1)] * 1297 + [T0 + timedelta(seconds=1)])
    assert rolling_background_max(
        conn, cutover=T0, now=T0 + timedelta(minutes=1)
    ) == 1
    assert conn.params["lookback"] == T0 - timedelta(hours=1)


def test_current_hour_is_counted_without_trial_starts():
    conn = FakeConnection([T0 - timedelta(minutes=1)] * 1297)
    assert rolling_background_max(
        conn, cutover=T0, now=T0 + timedelta(minutes=1)
    ) == 1297


def test_current_hour_exact_expiry():
    conn = FakeConnection([T0 - timedelta(hours=1)] * 1297)
    assert rolling_background_max(conn, cutover=T0, now=T0) == 0


def test_pretrial_context_plus_trial_start():
    conn = FakeConnection(
        [T0 - timedelta(seconds=1)] * 1296 + [T0 + timedelta(seconds=1)]
    )
    assert rolling_background_max(
        conn, cutover=T0, now=T0 + timedelta(seconds=2)
    ) == 1297


def test_old_peak_expired_from_current_hour():
    conn = FakeConnection(
        [T0 - timedelta(minutes=59)] * 1297
    )
    # The current window still contains 1297 starts immediately after T0.
    assert rolling_background_max(conn, cutover=T0, now=T0) == 1297
    # Later, all those starts expire; no historical trial start exists.
    assert rolling_background_max(
        conn, cutover=T0, now=T0 + timedelta(minutes=2)
    ) == 0
