"""Deterministic, zero-network model for mediated outbound dispatch.

NOT production code. This models a single atomic admission+fake-send boundary,
which is an assumption to validate, not a property of a Python HTTP call.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Callable
from uuid import UUID


class DispatchDenied(RuntimeError):
    pass


@dataclass(frozen=True)
class Submission:
    job_id: int
    attempt: int
    resource: str
    collector_uuid: UUID
    lease_token: UUID
    egress_key: str

    @property
    def key(self) -> tuple[int, int, str, UUID]:
        return (self.job_id, self.attempt, self.resource, self.lease_token)


@dataclass
class FakeDispatchAuthority:
    """Single-threaded model; no DB, no HTTP, no real distributed locking."""

    limit: int = 1296
    interval: timedelta = timedelta(hours=1)
    sent: deque[datetime] = field(default_factory=deque)
    completed: set[tuple[int, int, str, UUID]] = field(default_factory=set)
    available: bool = True

    def submit(
        self,
        request: Submission,
        *,
        at: datetime,
        owns_lease: Callable[[Submission, datetime], bool],
        fake_transport: Callable[[Submission], None],
    ) -> bool:
        """Return False for idempotent replay, raise for rejected submission.

        Fake transport is called only after modeled atomic validation/admission.
        A real transport cannot inherit this atomicity without additional proof.
        """
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("authoritative timestamp must be timezone-aware")
        now = at.astimezone(timezone.utc)
        if not self.available:
            raise DispatchDenied("authority unavailable")
        if not request.egress_key or request.resource not in ("detailed", "weapons", "vehicles"):
            raise DispatchDenied("invalid request")
        if request.key in self.completed:
            return False
        if not owns_lease(request, now):
            raise DispatchDenied("stale owner")
        # Half-open interval (now - 1h, now]: exactly one hour old is excluded.
        while self.sent and self.sent[0] <= now - self.interval:
            self.sent.popleft()
        if len(self.sent) >= self.limit:
            raise DispatchDenied("hourly budget exhausted")
        # The model treats recording and fake dispatch as indivisible.
        # In production, network send and DB commit are NOT indivisible.
        self.sent.append(now)
        self.completed.add(request.key)
        fake_transport(request)
        return True
