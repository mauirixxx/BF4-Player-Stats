"""Offline adversarial model: ledger admission != physical HTTP transmission.

Pure deterministic integer-second simulations. No sockets, database, workers,
clock reads, or production integration. See physical-dispatch safety design.
"""
from __future__ import annotations

from dataclasses import dataclass

HOUR_SECONDS = 3600
GLOBAL_LIMIT = 1296


@dataclass(frozen=True)
class Attempt:
    identity: str
    admitted_at: int
    physical_send_at: int | None = None


def count_rolling(times: list[int], *, at: int, window: int = HOUR_SECONDS) -> int:
    """Count sends in the half-open interval (at-window, at]."""
    if window <= 0:
        raise ValueError("window must be positive")
    return sum(at - window < timestamp <= at for timestamp in times)


def admission_windows_safe(attempts: list[Attempt], *, limit: int = GLOBAL_LIMIT) -> bool:
    """Check all relevant admission-time windows; does not prove send safety."""
    if limit <= 0:
        raise ValueError("limit must be positive")
    admissions = [a.admitted_at for a in attempts]
    return all(count_rolling(admissions, at=t) <= limit for t in admissions)


def physical_windows_safe(attempts: list[Attempt], *, limit: int = GLOBAL_LIMIT) -> bool:
    """Check all relevant physical-send windows, assuming known send timestamps."""
    if limit <= 0:
        raise ValueError("limit must be positive")
    sends = [a.physical_send_at for a in attempts if a.physical_send_at is not None]
    return all(count_rolling(sends, at=t) <= limit for t in sends)


def delayed_send_counterexample(*, limit: int = GLOBAL_LIMIT) -> list[Attempt]:
    """Admitted windows obey limit; an arbitrarily delayed send violates it.

    The delayed authorization at t=0 is no longer counted at t=3601.
    A fresh full cohort is admitted at t=3601 and physically sent immediately.
    The old worker resumes and sends at t=3602.
    """
    if limit <= 0:
        raise ValueError("limit must be positive")
    return [
        Attempt("stalled", 0, 3602),
        *[Attempt(f"fresh-{i}", 3601, 3601) for i in range(limit)],
    ]


def ttl_check_then_pause_counterexample(*, ttl_seconds: int = 5) -> Attempt:
    """Passing a TTL check does not constrain a subsequent arbitrary pause."""
    if ttl_seconds <= 0:
        raise ValueError("TTL must be positive")
    # Worker checks authorization at t=1 (< ttl), then suspends.
    # The send occurs after expiry; checking again has the same race.
    return Attempt("checked-at-1-then-paused", 0, ttl_seconds + 3601)


def worst_case_possible_usage(
    admitted: list[Attempt], *, at: int, unresolved_ids: set[str],
    window: int = HOUR_SECONDS,
) -> int:
    """Conservative capacity burden: recent known sends plus unresolved permits.

    Unresolved identities remain charged regardless of admission age. This is
    intentionally fail-closed and is NOT a full distributed rate limiter.
    """
    if len({a.identity for a in admitted}) != len(admitted):
        raise ValueError("duplicate identities")
    known = [a.physical_send_at for a in admitted
             if a.identity not in unresolved_ids and a.physical_send_at is not None]
    unknown = sum(a.identity in unresolved_ids for a in admitted)
    return count_rolling(known, at=at, window=window) + unknown
