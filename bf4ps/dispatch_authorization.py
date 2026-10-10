"""Pure dispatch-authorization policy prototype (not wired to HTTP).

This module checks an already issued permit; it does not create permits,
query PostgreSQL, or make network dispatch atomic. In particular, callers
must not interpret a successful check as permission to dispatch after an
arbitrary process pause. See docs/stage9c-t4-lease-expiry-safety-test-design.md.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID


class DispatchAuthorizationRejected(RuntimeError):
    """A dispatch authorization is missing, stale, or inconsistent."""


@dataclass(frozen=True)
class DispatchAuthorization:
    job_id: int
    attempt_number: int
    collector_uuid: UUID
    lease_token: UUID
    issued_at: datetime
    expires_at: datetime


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("dispatch authorization timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def validate_dispatch_authorization(
    permit: DispatchAuthorization,
    *,
    observed_at: datetime,
    job_id: int,
    attempt_number: int,
    collector_uuid: UUID,
    lease_token: UUID,
) -> None:
    """Reject invalid permits; use an authoritative clock at the call site.

    This is a *policy* check only. It is not an atomic network handoff,
    cannot guarantee a strict actual-HTTP rolling-hour ceiling, and is
    intentionally not integrated into any production collector.
    """
    issued = _utc(permit.issued_at)
    expiry = _utc(permit.expires_at)
    observed = _utc(observed_at)
    if permit.job_id <= 0 or permit.attempt_number <= 0:
        raise DispatchAuthorizationRejected("invalid job or attempt")
    if issued >= expiry:
        raise DispatchAuthorizationRejected("invalid authorization interval")
    if (permit.job_id, permit.attempt_number, permit.collector_uuid, permit.lease_token) != (
        job_id, attempt_number, collector_uuid, lease_token
    ):
        raise DispatchAuthorizationRejected("authorization ownership mismatch")
    if not (issued <= observed < expiry):
        raise DispatchAuthorizationRejected("authorization outside valid time window")
