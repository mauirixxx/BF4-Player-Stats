"""Pure accounting model for a future unified background-dispatch ledger.

DESIGN TEST SUPPORT ONLY. No SQL, HTTP, database writes, or production wiring.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True)
class BudgetEvidence:
    """A stable logical attempt identity across event/reservation/dispatch sources."""

    identity: tuple[int, int, str, str]
    source: str  # started, reserved, dispatch
    occurred_at: datetime
    expires_at: datetime | None = None


def unified_rolling_usage(
    evidence: list[BudgetEvidence], *, at: datetime, interval: timedelta = timedelta(hours=1)
) -> int:
    """Count unique active attempt identities, not raw rows from three ledgers.

    Reservations are active until lease expiry; started/dispatch records count
    for the rolling window. This does NOT model late HTTP or source completeness.
    """
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("at must be timezone-aware")
    now = at.astimezone(timezone.utc)
    identities: set[tuple[int, int, str, str]] = set()
    for item in evidence:
        if item.source not in ("started", "reserved", "dispatch"):
            raise ValueError("unknown evidence source")
        if item.occurred_at.tzinfo is None or item.occurred_at.utcoffset() is None:
            raise ValueError("evidence time must be timezone-aware")
        occurred = item.occurred_at.astimezone(timezone.utc)
        if item.source == "reserved":
            if item.expires_at is None or item.expires_at.tzinfo is None or item.expires_at.utcoffset() is None:
                raise ValueError("reservation expiry must be timezone-aware")
            active = item.expires_at.astimezone(timezone.utc) > now
        else:
            active = now - interval < occurred <= now
        if active:
            identities.add(item.identity)
    return len(identities)
