import logging

import pytest

from bf4ps.discovery_service import CycleFailureLogger, seconds_until_due


def test_seconds_until_due_uses_earliest_job():
    assert seconds_until_due(100.0, 160.0, 400.0) == 60.0
    assert seconds_until_due(100.0, 160.0, 120.0) == 20.0


def test_seconds_until_due_never_returns_negative():
    assert seconds_until_due(100.0, 90.0, 120.0) == 0.0


def test_cycle_failure_logger_suppresses_repeated_tracebacks_and_logs_recovery(caplog):
    failures = CycleFailureLogger("discovery")

    with caplog.at_level(logging.INFO, logger="bf4ps.discovery_service"):
        try:
            raise RuntimeError("source unavailable")
        except RuntimeError as exc:
            failures.failed(exc)

        assert failures.consecutive_failures == 1

        try:
            raise RuntimeError("source still unavailable")
        except RuntimeError as exc:
            failures.failed(exc)

        assert failures.consecutive_failures == 2
        failures.succeeded()

    assert failures.consecutive_failures == 0
    messages = [record.getMessage() for record in caplog.records]
    assert messages[0] == "BF4SW discovery cycle failed"
    assert "consecutive_failures=2" in messages[1]
    assert "source still unavailable" in messages[1]
    assert messages[2] == "BF4SW discovery cycle recovered after 2 consecutive failure(s)"
    assert caplog.records[0].exc_info is not None
    assert caplog.records[1].exc_info is None
