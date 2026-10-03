from __future__ import annotations

import argparse
import logging
import signal
import time
from datetime import timedelta

from sqlalchemy import create_engine, text

from bf4ps.config import database_url
from bf4ps.discovery import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_RECONCILE_OVERLAP_MINUTES,
    DEFAULT_RECONCILE_WINDOW_HOURS,
    bf4sw_database_url,
    run_catch_up,
    run_reconciliation,
)

LOGGER = logging.getLogger("bf4ps.discovery_service")
DEFAULT_DISCOVERY_INTERVAL_SECONDS = 60
DEFAULT_RECONCILE_INTERVAL_SECONDS = 300
ADVISORY_LOCK_KEY = 0x4246345053444953  # "BF4PSDIS"


def acquire_service_lock(connection) -> bool:
    return bool(
        connection.execute(
            text("SELECT pg_try_advisory_lock(:lock_key)"),
            {"lock_key": ADVISORY_LOCK_KEY},
        ).scalar_one()
    )


def release_service_lock(connection) -> None:
    connection.execute(
        text("SELECT pg_advisory_unlock(:lock_key)"),
        {"lock_key": ADVISORY_LOCK_KEY},
    )


def run_discovery_cycle(source_engine, destination_engine, *, batch_size: int) -> None:
    run_catch_up(source_engine, destination_engine, batch_size=batch_size)


def run_reconciliation_cycle(
    source_engine,
    destination_engine,
    *,
    initial_window_hours: int,
    overlap_minutes: int,
) -> None:
    with source_engine.connect() as source:
        with destination_engine.begin() as destination:
            since, through, alias_rows, identities = run_reconciliation(
                source,
                destination,
                initial_window_hours=initial_window_hours,
                overlap_minutes=overlap_minutes,
            )
    LOGGER.info(
        "BF4SW reconciliation complete: since=%s through=%s alias_rows=%d identities=%d",
        since.isoformat(),
        through.isoformat(),
        alias_rows,
        identities,
    )


def seconds_until_due(now: float, discovery_due: float, reconcile_due: float) -> float:
    return max(0.0, min(discovery_due, reconcile_due) - now)


class CycleFailureLogger:
    """Log the first consecutive failure with traceback, then stay concise until recovery."""

    def __init__(self, operation: str):
        self.operation = operation
        self.consecutive_failures = 0

    def failed(self, exc: Exception) -> None:
        self.consecutive_failures += 1
        if self.consecutive_failures == 1:
            LOGGER.exception("BF4SW %s cycle failed", self.operation)
        else:
            LOGGER.error(
                "BF4SW %s cycle still failing: consecutive_failures=%d error=%s: %s",
                self.operation,
                self.consecutive_failures,
                type(exc).__name__,
                exc,
            )

    def succeeded(self) -> None:
        if self.consecutive_failures:
            LOGGER.info(
                "BF4SW %s cycle recovered after %d consecutive failure(s)",
                self.operation,
                self.consecutive_failures,
            )
            self.consecutive_failures = 0


def run_service(
    source_engine,
    destination_engine,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    discovery_interval_seconds: int = DEFAULT_DISCOVERY_INTERVAL_SECONDS,
    reconcile_interval_seconds: int = DEFAULT_RECONCILE_INTERVAL_SECONDS,
    initial_window_hours: int = DEFAULT_RECONCILE_WINDOW_HOURS,
    overlap_minutes: int = DEFAULT_RECONCILE_OVERLAP_MINUTES,
) -> int:
    if discovery_interval_seconds < 1:
        raise ValueError("discovery_interval_seconds must be at least 1")
    if reconcile_interval_seconds < 1:
        raise ValueError("reconcile_interval_seconds must be at least 1")

    stopping = False
    discovery_failures = CycleFailureLogger("discovery")
    reconciliation_failures = CycleFailureLogger("reconciliation")

    def request_stop(signum, frame):  # noqa: ARG001
        nonlocal stopping
        stopping = True
        LOGGER.info("Shutdown requested by signal %s", signum)

    previous_handlers = {}
    for sig in (signal.SIGINT, signal.SIGTERM):
        previous_handlers[sig] = signal.signal(sig, request_stop)

    lock_connection = destination_engine.connect()
    try:
        if not acquire_service_lock(lock_connection):
            LOGGER.error("Another BF4PS discovery service already holds the PostgreSQL advisory lock")
            return 2

        LOGGER.info("BF4PS discovery service lock acquired")

        # Startup deliberately performs both jobs immediately. Each job is
        # isolated so a temporary failure in one does not prevent the other
        # from running or advance the failed operation's durable state.
        try:
            run_discovery_cycle(source_engine, destination_engine, batch_size=batch_size)
        except Exception as exc:
            discovery_failures.failed(exc)
        else:
            discovery_failures.succeeded()

        try:
            run_reconciliation_cycle(
                source_engine,
                destination_engine,
                initial_window_hours=initial_window_hours,
                overlap_minutes=overlap_minutes,
            )
        except Exception as exc:
            reconciliation_failures.failed(exc)
        else:
            reconciliation_failures.succeeded()

        now = time.monotonic()
        discovery_due = now + discovery_interval_seconds
        reconcile_due = now + reconcile_interval_seconds

        while not stopping:
            now = time.monotonic()
            if now >= discovery_due:
                try:
                    run_discovery_cycle(source_engine, destination_engine, batch_size=batch_size)
                except Exception as exc:
                    discovery_failures.failed(exc)
                else:
                    discovery_failures.succeeded()
                discovery_due = time.monotonic() + discovery_interval_seconds

            now = time.monotonic()
            if now >= reconcile_due:
                try:
                    run_reconciliation_cycle(
                        source_engine,
                        destination_engine,
                        initial_window_hours=initial_window_hours,
                        overlap_minutes=overlap_minutes,
                    )
                except Exception as exc:
                    reconciliation_failures.failed(exc)
                else:
                    reconciliation_failures.succeeded()
                reconcile_due = time.monotonic() + reconcile_interval_seconds

            if stopping:
                break
            time.sleep(min(1.0, seconds_until_due(time.monotonic(), discovery_due, reconcile_due)))

        LOGGER.info("BF4PS discovery service stopping")
        return 0
    finally:
        try:
            if not lock_connection.closed:
                release_service_lock(lock_connection)
        except Exception:
            LOGGER.exception("Failed to release BF4PS discovery service advisory lock")
        lock_connection.close()
        for sig, handler in previous_handlers.items():
            signal.signal(sig, handler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Continuously discover and reconcile BF4SW soldiers into BF4PS.")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--discovery-interval-seconds", type=int, default=DEFAULT_DISCOVERY_INTERVAL_SECONDS)
    parser.add_argument("--reconcile-interval-seconds", type=int, default=DEFAULT_RECONCILE_INTERVAL_SECONDS)
    parser.add_argument("--reconcile-window-hours", type=int, default=DEFAULT_RECONCILE_WINDOW_HOURS)
    parser.add_argument("--reconcile-overlap-minutes", type=int, default=DEFAULT_RECONCILE_OVERLAP_MINUTES)
    parser.add_argument("--log-level", default="INFO", choices=("DEBUG", "INFO", "WARNING", "ERROR"))
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    source_engine = create_engine(bf4sw_database_url())
    destination_engine = create_engine(database_url())
    raise SystemExit(
        run_service(
            source_engine,
            destination_engine,
            batch_size=args.batch_size,
            discovery_interval_seconds=args.discovery_interval_seconds,
            reconcile_interval_seconds=args.reconcile_interval_seconds,
            initial_window_hours=args.reconcile_window_hours,
            overlap_minutes=args.reconcile_overlap_minutes,
        )
    )


if __name__ == "__main__":
    main()
