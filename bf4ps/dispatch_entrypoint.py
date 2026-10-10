"""Shared, zero-network-capable dispatch handoff prototype.

NOT wired to collectors. This policy check and callback are not atomic:
a process paused after validation may invoke transport after expiry.
"""
from __future__ import annotations

from datetime import datetime
from typing import Callable, TypeVar
from uuid import UUID

from bf4ps.dispatch_authorization import (
    DispatchAuthorization,
    validate_dispatch_authorization,
)

T = TypeVar("T")


def dispatch_with_authorization(
    permit: DispatchAuthorization,
    *,
    observed_at: datetime,
    job_id: int,
    attempt_number: int,
    collector_uuid: UUID,
    lease_token: UUID,
    transport: Callable[[], T],
) -> T:
    """Validate a bounded permit, then invoke an injected transport.

    Only the caller-supplied transport runs; this module does no HTTP.
    This is a *testable policy entry point*, not a production safety barrier.
    """
    validate_dispatch_authorization(
        permit,
        observed_at=observed_at,
        job_id=job_id,
        attempt_number=attempt_number,
        collector_uuid=collector_uuid,
        lease_token=lease_token,
    )
    return transport()
