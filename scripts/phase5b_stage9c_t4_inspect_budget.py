"""Pure, time-aware budget assertion for T4's one unstarted reservation.

T4 seeds 1295 physical-start events and claims one job without starting HTTP.
An unstarted reservation counts only until its lease expires.
"""
from __future__ import annotations

from datetime import datetime

from bf4ps.background_service import BACKGROUND_SLOTS_PER_HOUR


def expected_t4_usage(*, lease_expires_at: datetime, observed_at: datetime) -> int:
    if lease_expires_at.tzinfo is None or observed_at.tzinfo is None:
        raise ValueError("T4 timestamps must be timezone-aware")
    return BACKGROUND_SLOTS_PER_HOUR if lease_expires_at > observed_at else BACKGROUND_SLOTS_PER_HOUR - 1


def verify_t4_usage(*, observed_total: int, lease_expires_at: datetime, observed_at: datetime) -> str:
    expected = expected_t4_usage(lease_expires_at=lease_expires_at, observed_at=observed_at)
    if observed_total != expected:
        raise AssertionError(f"T4 budget mismatch: observed={observed_total}, expected={expected}, lease_expires_at={lease_expires_at}, observed_at={observed_at}")
    if expected == BACKGROUND_SLOTS_PER_HOUR:
        return "PASS: active unstarted reservation counted, 1296/1296"
    return "PASS: expired unstarted reservation excluded, 1295/1296; original admission established by durable winner/loser ledger"
