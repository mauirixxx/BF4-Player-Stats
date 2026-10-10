"""Conservative three-source D2 budget characterization; offline only.

Incomplete started-event identities count independently; multiple started
events with the same full identity also count independently because a repeated
transport cannot yet be ruled out. This is not a physical-send guarantee.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True)
class ReconciliationEvidence:
    source: str
    job_id: int | None
    attempt_number: int | None
    resource: str | None
    lease_token: str | None
    occurred_at: datetime
    expires_at: datetime | None = None


def conservative_background_usage(
    evidence: list[ReconciliationEvidence], *, at: datetime,
    interval: timedelta = timedelta(hours=1),
) -> int:
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("at must be timezone-aware")
    if interval <= timedelta(0):
        raise ValueError("interval must be positive")
    now = at.astimezone(timezone.utc)
    full: set[tuple[int, int, str, str]] = set()
    unmatched = 0
    started_counts: dict[tuple[int, int, str, str], int] = {}
    for row in evidence:
        if row.source not in ("started", "reserved", "dispatch"):
            raise ValueError("unknown source")
        if row.occurred_at.tzinfo is None or row.occurred_at.utcoffset() is None:
            raise ValueError("evidence time must be timezone-aware")
        occurred = row.occurred_at.astimezone(timezone.utc)
        if row.source == "reserved":
            if row.expires_at is None or row.expires_at.tzinfo is None or row.expires_at.utcoffset() is None:
                raise ValueError("reservation expiry must be timezone-aware")
            active = row.expires_at.astimezone(timezone.utc) > now
        else:
            active = now - interval < occurred <= now
        if not active:
            continue
        key_parts = (row.job_id, row.attempt_number, row.resource, row.lease_token)
        if any(part is None for part in key_parts):
            # Fail closed on incomplete started evidence; incomplete evidence
            # in any source is conservatively charged, never silently joined.
            unmatched += 1
            continue
        key = (row.job_id, row.attempt_number, row.resource, row.lease_token)
        full.add(key)
        if row.source == "started":
            started_counts[key] = started_counts.get(key, 0) + 1
    # Each duplicate started event beyond the first is additional potential
    # send evidence, even if a dispatch row has the same identity.
    extra_starts = sum(max(0, count - 1) for count in started_counts.values())
    return len(full) + unmatched + extra_starts
