"""D2 scratch-only atomic SQL-accounted dispatch experiment.

NOT production admission: deliberately lacks queue ownership, supervision,
fairness and physical-send checks. Must never be called by a collector.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from bf4ps.dispatch_budget_sql import read_conservative_background_usage

LOCK = text("SELECT pg_advisory_xact_lock(hashtext('bf4ps:phase5b-background-service'))")
CLOCK = text("SELECT clock_timestamp()")
INSERT = text(
    "INSERT INTO outbound_dispatches "
    "(dispatch_id,job_id,attempt_number,resource,lease_token,collector_uuid,"
    "egress_key,lane,payload_fingerprint,admitted_at) "
    "VALUES (:dispatch_id,:job_id,:attempt_number,:resource,:lease_token,"
    ":collector_uuid,:egress_key,'background',:payload_fingerprint,:at)"
)


@dataclass(frozen=True)
class SyntheticDispatch:
    dispatch_id: UUID
    job_id: int
    attempt_number: int
    resource: str
    lease_token: UUID
    collector_uuid: UUID
    egress_key: str
    payload_fingerprint: str


def try_synthetic_admission(conn: Connection, candidate: SyntheticDispatch, *, capacity: int = 1296) -> bool:
    """Return admission outcome. Caller MUST own an open transaction.

    The same transaction must commit the inserted row. Never return a
    transport permit: this experiment is strictly ledger accounting.
    """
    if not conn.in_transaction():
        raise RuntimeError("transaction required")
    if capacity <= 0 or capacity > 1296:
        raise ValueError("invalid scratch capacity")
    conn.execute(LOCK)
    at = conn.execute(CLOCK).scalar_one()
    usage = read_conservative_background_usage(conn, at=at)
    if usage >= capacity:
        return False
    conn.execute(INSERT, {
        "dispatch_id": candidate.dispatch_id,
        "job_id": candidate.job_id,
        "attempt_number": candidate.attempt_number,
        "resource": candidate.resource,
        "lease_token": candidate.lease_token,
        "collector_uuid": candidate.collector_uuid,
        "egress_key": candidate.egress_key,
        "payload_fingerprint": candidate.payload_fingerprint,
        "at": at,
    })
    return True
