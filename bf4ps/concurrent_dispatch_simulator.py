"""Zero-network concurrent admission model; NOT a PostgreSQL implementation.

Thread locking here models the required serialization point. It does not prove
cross-process/database locking, transport atomicity, or arbitrary-pause safety.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Callable

from bf4ps.dispatch_simulator import DispatchDenied, Submission


@dataclass
class SharedAdmissionLedger:
    limit: int = 1296
    lock: Lock = field(default_factory=Lock)
    admissions: dict[tuple, datetime] = field(default_factory=dict)

    def admit(
        self,
        request: Submission,
        *,
        at: datetime,
        owns_lease: Callable[[Submission, datetime], bool],
    ) -> bool:
        """Atomic in-memory test analogue of a serialized DB transaction.

        True = newly admitted; False = existing identity, never a new send grant.
        """
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("authoritative timestamp must be timezone-aware")
        now = at.astimezone(timezone.utc)
        with self.lock:
            if request.key in self.admissions:
                return False
            if not owns_lease(request, now):
                raise DispatchDenied("stale owner")
            count = sum(
                1 for admitted_at in self.admissions.values()
                if now - timedelta(hours=1) < admitted_at <= now
            )
            if count >= self.limit:
                raise DispatchDenied("hourly budget exhausted")
            self.admissions[request.key] = now
            return True
