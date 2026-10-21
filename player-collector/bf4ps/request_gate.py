"""PostgreSQL-coordinated outbound request pacing for BF4PS collectors.

The gate is keyed by egress identity, not collector process. Every contender
sharing an egress_key serializes its reservation through one PostgreSQL row.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import Connection, text


@dataclass(frozen=True)
class RequestPermit:
    egress_key: str
    reserved_at: datetime
    wait_seconds: float
    next_request_at: datetime


def _validate(egress_key: str, interval_seconds: float) -> str:
    key = egress_key.strip()
    if not key:
        raise ValueError("egress_key must not be empty")
    if not math.isfinite(interval_seconds) or interval_seconds < 0:
        raise ValueError("interval_seconds must be finite and >= 0")
    return key


def reserve_request_slot(
    conn: Connection,
    *,
    egress_key: str,
    interval_seconds: float,
) -> RequestPermit:
    """Atomically reserve the next legal request time for one egress.

    Commit the surrounding transaction before issuing HTTP. This function does
    not sleep while holding the gate row lock; it reserves a future slot.
    """
    key = _validate(egress_key, interval_seconds)
    conn.execute(
        text("""
            INSERT INTO request_gates (egress_key, next_request_at, updated_at)
            VALUES (:egress_key, now(), now())
            ON CONFLICT (egress_key) DO NOTHING
        """),
        {"egress_key": key},
    )
    gate = conn.execute(
        text("""
            SELECT next_request_at, clock_timestamp() AS db_now
            FROM request_gates
            WHERE egress_key = :egress_key
            FOR UPDATE
        """),
        {"egress_key": key},
    ).mappings().one()
    db_now = gate["db_now"]
    reserved_at = max(db_now, gate["next_request_at"])
    next_request_at = reserved_at + timedelta(seconds=interval_seconds)
    conn.execute(
        text("""
            UPDATE request_gates
            SET next_request_at = :next_request_at,
                updated_at = now()
            WHERE egress_key = :egress_key
        """),
        {"egress_key": key, "next_request_at": next_request_at},
    )
    return RequestPermit(
        egress_key=key,
        reserved_at=reserved_at,
        wait_seconds=max(0.0, (reserved_at - db_now).total_seconds()),
        next_request_at=next_request_at,
    )


def wait_for_permit(permit: RequestPermit) -> None:
    """Wait locally until the database-reserved request time."""
    remaining = (permit.reserved_at - datetime.now(timezone.utc)).total_seconds()
    if remaining > 0:
        time.sleep(remaining)
