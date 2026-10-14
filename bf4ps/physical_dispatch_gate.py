"""Durable fleet-wide physical HTTP admission.

This is an authorization primitive, not an HTTP client. Callers MUST commit the
transaction and mark the dispatch may_have_sent before invoking the network.
No production collector should be undrained until all HTTP paths use it.
"""
from __future__ import annotations

from dataclasses import dataclass
from contextlib import contextmanager
from hashlib import sha256
from typing import Iterator
from sqlalchemy.engine import Engine
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Connection

PHYSICAL_DISPATCHES_PER_HOUR = 4800
GATE_LOCK_KEY = "bf4ps:production-physical-dispatch-v1"


class PhysicalDispatchBudgetExhausted(RuntimeError):
    """No physical HTTP capacity remains in the rolling hour."""


@dataclass(frozen=True)
class PhysicalDispatchPermit:
    dispatch_id: UUID
    admitted_at: datetime
    remaining: int


def authorize_physical_dispatch(
    conn: Connection,
    *,
    job_id: int,
    attempt_number: int,
    request_ordinal: int,
    resource: str,
    lease_token: UUID,
    collector_uuid: UUID,
    egress_key: str,
    lane: str,
    payload_fingerprint: str,
) -> PhysicalDispatchPermit:
    """Atomically authorize one network attempt under the fleet-wide ceiling.

    Caller must COMMIT before sending. Admission counts all lanes and egress
    identities, including rows whose request was never sent (fail conservative).
    PostgreSQL's clock is authoritative; the transaction advisory lock
    serializes admission decisions across collector processes.
    """
    if job_id <= 0 or attempt_number <= 0 or request_ordinal <= 0:
        raise ValueError("job_id, attempt_number, request_ordinal must be positive")
    if not egress_key.strip() or not payload_fingerprint.strip():
        raise ValueError("egress_key and payload_fingerprint must be nonempty")
    if resource not in ("detailed", "profile", "weapons", "vehicles"):
        raise ValueError("unsupported resource")
    if lane not in ("background", "interactive"):
        raise ValueError("unsupported lane")

    # A stale repeatable-read snapshot could hide another worker's commits.
    isolation = conn.get_isolation_level().upper()
    if isolation != "READ COMMITTED":
        raise RuntimeError(f"physical dispatch gate requires READ COMMITTED, got {isolation}")

    conn.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": GATE_LOCK_KEY})
    db_now = conn.execute(text("SELECT clock_timestamp()")).scalar_one()
    used = int(conn.execute(
        text("""
            SELECT COUNT(*)
            FROM outbound_dispatches
            WHERE admitted_at > :cutoff AND admitted_at <= :now
        """),
        {"cutoff": db_now - timedelta(seconds=3600), "now": db_now},
    ).scalar_one())
    if used >= PHYSICAL_DISPATCHES_PER_HOUR:
        raise PhysicalDispatchBudgetExhausted(
            f"fleet-wide rolling 3600s physical dispatch ceiling reached ({used})"
        )
    dispatch_id = uuid4()
    conn.execute(
        text("""
            INSERT INTO outbound_dispatches
                (dispatch_id, job_id, attempt_number, request_ordinal,
                 resource, lease_token, collector_uuid, egress_key, lane,
                 payload_fingerprint, admitted_at, phase)
            VALUES
                (:dispatch_id, :job_id, :attempt_number, :request_ordinal,
                 :resource, :lease_token, :collector_uuid, :egress_key, :lane,
                 :payload_fingerprint, :admitted_at, 'admitted')
        """),
        {
            "dispatch_id": dispatch_id,
            "job_id": job_id,
            "attempt_number": attempt_number,
            "request_ordinal": request_ordinal,
            "resource": resource,
            "lease_token": lease_token,
            "collector_uuid": collector_uuid,
            "egress_key": egress_key,
            "lane": lane,
            "payload_fingerprint": payload_fingerprint,
            "admitted_at": db_now,
        },
    )
    return PhysicalDispatchPermit(dispatch_id, db_now, PHYSICAL_DISPATCHES_PER_HOUR - used - 1)


def mark_physical_dispatch_may_have_sent(conn: Connection, dispatch_id: UUID) -> None:
    """Durably mark possible network send; caller must commit before HTTP."""
    changed = conn.execute(
        text("""
            UPDATE outbound_dispatches
            SET phase = 'may_have_sent', send_marked_at = clock_timestamp()
            WHERE dispatch_id = :dispatch_id AND phase = 'admitted'
        """),
        {"dispatch_id": dispatch_id},
    )
    if changed.rowcount != 1:
        raise RuntimeError("dispatch is missing or has already been marked sent")


def acknowledge_physical_dispatch(conn: Connection, dispatch_id: UUID) -> None:
    """Acknowledge completed transport; do not delete or refund budget."""
    changed = conn.execute(
        text("""
            UPDATE outbound_dispatches
            SET phase = 'acknowledged', acknowledged_at = clock_timestamp()
            WHERE dispatch_id = :dispatch_id AND phase = 'may_have_sent'
        """),
        {"dispatch_id": dispatch_id},
    )
    if changed.rowcount != 1:
        raise RuntimeError("dispatch not in may_have_sent state")


@contextmanager
def authorized_http_attempt(
    engine: Engine,
    *,
    job,
    identity,
    resource: str,
    request_ordinal: int,
    request_label: str,
) -> Iterator[PhysicalDispatchPermit]:
    """Fail-closed durable authorization for one physical outbound HTTP call.

    Authorization and may-have-sent evidence commit before caller can enter
    the body. This is not a retry or redirect wrapper; callers must disable
    implicit HTTP redirects and retries or authorize each subsequent attempt.
    """
    if not request_label.strip():
        raise ValueError("request_label must not be blank")
    with engine.begin() as conn:
        owned = conn.execute(
            text("""
                SELECT 1 FROM collection_jobs
                WHERE job_id=:job_id AND collector_uuid=:collector_uuid
                  AND lease_token=:lease_token AND status='running'
                  AND lease_expires_at > now()
                FOR UPDATE
            """),
            dict(job_id=job.job_id, collector_uuid=job.collector_uuid,
                 lease_token=job.lease_token),
        ).one_or_none()
        if owned is None:
            raise RuntimeError("physical HTTP authorization rejected: lease not owned")
        permit = authorize_physical_dispatch(
            conn, job_id=job.job_id, attempt_number=job.attempt_count,
            request_ordinal=request_ordinal, resource=resource,
            lease_token=job.lease_token, collector_uuid=job.collector_uuid,
            egress_key=identity.egress_key, lane=job.lane,
            payload_fingerprint=sha256(request_label.encode("utf-8")).hexdigest(),
        )
        mark_physical_dispatch_may_have_sent(conn, permit.dispatch_id)
    # A transport failure leaves conservative may_have_sent evidence.
    # Successful return alone permits acknowledgement.
    yield permit
    with engine.begin() as conn:
        acknowledge_physical_dispatch(conn, permit.dispatch_id)
