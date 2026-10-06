"""Frozen Phase 5B resource-specific retry policy."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Connection

SUPPORTED_RETRY_RESOURCES = ("detailed", "weapons", "vehicles")
RETRY_BACKOFF_SECONDS = (15 * 60, 60 * 60, 6 * 60 * 60, 24 * 60 * 60)


def retry_delay_seconds(consecutive_failure_number: int) -> int:
    """Return the frozen delay for the failure being recorded."""
    if consecutive_failure_number <= 0:
        raise ValueError("consecutive_failure_number must be positive")
    index = min(consecutive_failure_number, len(RETRY_BACKOFF_SECONDS)) - 1
    return RETRY_BACKOFF_SECONDS[index]


def retry_delay_for_failure(
    conn: Connection,
    *,
    soldier_id: int,
    resource: str,
) -> int:
    """Read current resource debt and return delay for the next failure."""
    if soldier_id <= 0:
        raise ValueError("soldier_id must be positive")
    if resource not in SUPPORTED_RETRY_RESOURCES:
        raise ValueError(f"unsupported retry resource: {resource!r}")

    column = f"{resource}_consecutive_failures"
    current = conn.execute(
        text(f"SELECT {column} FROM collection_state WHERE soldier_id = :soldier_id"),
        {"soldier_id": soldier_id},
    ).scalar_one()
    return retry_delay_seconds(int(current) + 1)
