"""Pure scheduling rules for user-initiated BF4 stat requests.

No database operations occur here. The transactional admission layer must
recheck these decisions while holding a per-soldier lock.
"""
from datetime import datetime, timedelta

COOLDOWN = timedelta(minutes=60)
RESOURCES = ('detailed', 'weapons', 'vehicles', 'profile')


def cooldown_remaining(*, last_accepted_at: datetime | None, now: datetime) -> timedelta:
    if now.tzinfo is None:
        raise ValueError('now must be timezone-aware')
    if last_accepted_at is None:
        return timedelta(0)
    if last_accepted_at.tzinfo is None:
        raise ValueError('last_accepted_at must be timezone-aware')
    return max(timedelta(0), last_accepted_at + COOLDOWN - now)


def refreshable_resources(*, last_success: dict[str, datetime | None], now: datetime) -> tuple[str, ...]:
    if now.tzinfo is None:
        raise ValueError('now must be timezone-aware')
    selected = []
    for resource in RESOURCES:
        stamp = last_success.get(resource)
        if stamp is None:
            selected.append(resource)
        elif stamp.tzinfo is None:
            raise ValueError('success timestamps must be timezone-aware')
        elif stamp <= now - COOLDOWN:
            selected.append(resource)
    return tuple(selected)