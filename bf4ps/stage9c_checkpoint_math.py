"""Pure, offline Stage 9C rolling-window audit arithmetic.

This module has no database, network, or service operations.
"""
from datetime import timedelta


def observed_rolling_max(events, *, supervision_start, checkpoint_at):
    """Maximum eligible physical starts in strict trailing-hour windows.

    events is an iterable of (event_id, occurred_at) pairs, already filtered
    to eligible background physical starts. Includes pre-supervision context.
    """
    if (supervision_start.tzinfo is None
            or supervision_start.utcoffset() is None
            or checkpoint_at.tzinfo is None
            or checkpoint_at.utcoffset() is None
            or checkpoint_at < supervision_start):
        raise ValueError("invalid supervision/checkpoint timestamps")
    ordered = sorted(events, key=lambda e: (e[1], e[0]))
    if any(t.tzinfo is None or t.utcoffset() is None
           or t <= supervision_start - timedelta(hours=1)
           or t > checkpoint_at for _, t in ordered):
        raise ValueError("events outside required observation interval")
    times = [t for _, t in ordered]
    left = 0
    maximum = 0
    for right, timestamp in enumerate(times):
        while left <= right and times[left] <= timestamp - timedelta(hours=1):
            left += 1
        if timestamp >= supervision_start:
            maximum = max(maximum, right - left + 1)
    current = sum(t > checkpoint_at - timedelta(hours=1) for t in times)
    return max(maximum, current)
