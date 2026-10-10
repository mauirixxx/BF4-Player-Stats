"""Crash/recovery model for mediated dispatch; fake transports only.

NOT production code. In-memory state models durable committed state, and
simulated crashes are explicit barriers. No real DB/network atomicity implied.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Callable

from bf4ps.dispatch_simulator import DispatchDenied, Submission


class DispatchPhase(str, Enum):
    ADMITTED = "admitted"
    MAY_HAVE_SENT = "may_have_sent"
    ACKNOWLEDGED = "acknowledged"


@dataclass
class DurableDispatchState:
    """Shared durable-state *model*, passed to new authority instances on restart."""

    budget_limit: int = 1296
    entries: dict[tuple, tuple[datetime, DispatchPhase]] = field(default_factory=dict)


class SimulatedCrash(BaseException):
    """Stops a fake process without invoking ordinary exception recovery."""


class RecoveryAuthority:
    def __init__(self, durable: DurableDispatchState):
        self.durable = durable

    def admit(
        self,
        request: Submission,
        *,
        at: datetime,
        owns_lease: Callable[[Submission, datetime], bool],
    ) -> bool:
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("authoritative timestamp must be timezone-aware")
        now = at.astimezone(timezone.utc)
        if request.key in self.durable.entries:
            return False
        if not owns_lease(request, now):
            raise DispatchDenied("stale owner")
        # Count committed admissions conservatively for the entire rolling hour.
        active = sum(
            1 for recorded_at, _ in self.durable.entries.values()
            if now - timedelta(hours=1) < recorded_at <= now
        )
        if active >= self.durable.budget_limit:
            raise DispatchDenied("hourly budget exhausted")
        self.durable.entries[request.key] = (now, DispatchPhase.ADMITTED)
        return True

    def send(
        self,
        request: Submission,
        *,
        fake_transport: Callable[[Submission], None],
        crash_after_mark: bool = False,
    ) -> bool:
        record = self.durable.entries.get(request.key)
        if record is None:
            raise DispatchDenied("not admitted")
        recorded_at, phase = record
        if phase is not DispatchPhase.ADMITTED:
            return False
        # Persist ambiguity BEFORE entering the transport. A crash here may
        # waste capacity, but cannot authorize an automatic replay.
        self.durable.entries[request.key] = (recorded_at, DispatchPhase.MAY_HAVE_SENT)
        if crash_after_mark:
            raise SimulatedCrash("crash after durable may-have-sent mark")
        fake_transport(request)
        self.durable.entries[request.key] = (recorded_at, DispatchPhase.ACKNOWLEDGED)
        return True

    def phase(self, request: Submission) -> DispatchPhase | None:
        record = self.durable.entries.get(request.key)
        return record[1] if record else None
