"""Transactional claim and completion of pending soldier verifications.

The caller must authorize and pace each physical HTTP attempt separately.
These functions perform NO network I/O and do not activate a worker.
"""
from dataclasses import dataclass
from uuid import UUID
from sqlalchemy import text


@dataclass(frozen=True)
class VerificationClaim:
    verification_id: int
    submitted_url: str
    attempt_count: int


def claim_verification(conn, *, collector_uuid: UUID, lease_seconds: int = 120):
    if not isinstance(collector_uuid, UUID) or not 15 <= lease_seconds <= 600:
        raise ValueError("invalid collector or lease duration")
    row = conn.execute(text("""
        WITH candidate AS (
          SELECT verification_id
          FROM manual_soldier_verifications
          WHERE status = 'pending'
             OR (status = 'claimed' AND lease_expires_at < clock_timestamp())
          ORDER BY submitted_at, verification_id
          FOR UPDATE SKIP LOCKED
          LIMIT 1
        )
        UPDATE manual_soldier_verifications AS v
        SET status = 'claimed', claimed_at = clock_timestamp(),
            lease_expires_at = clock_timestamp() + (:seconds * interval '1 second'),
            collector_uuid = :collector, attempt_count = v.attempt_count + 1
        FROM candidate
        WHERE v.verification_id = candidate.verification_id
        RETURNING v.verification_id, v.submitted_url, v.attempt_count
    """), {"collector": collector_uuid, "seconds": lease_seconds}).one_or_none()
    if row is None:
        return None
    return VerificationClaim(int(row.verification_id), row.submitted_url, int(row.attempt_count))


def finish_verification(conn, *, verification_id: int, collector_uuid: UUID,
                        soldier_id: int | None = None, error: str | None = None):
    if verification_id <= 0 or not isinstance(collector_uuid, UUID):
        raise ValueError("invalid verification claim")
    if (soldier_id is None) == (error is None):
        raise ValueError("supply exactly one of soldier_id or error")
    if soldier_id is not None and soldier_id <= 0:
        raise ValueError("invalid soldier ID")
    result = conn.execute(text("""
        UPDATE manual_soldier_verifications
        SET status = CASE WHEN :soldier_id IS NULL THEN 'rejected' ELSE 'verified' END,
            soldier_id = :soldier_id, last_error = :error,
            lease_expires_at = NULL
        WHERE verification_id = :id AND collector_uuid = :collector
          AND status = 'claimed' AND lease_expires_at > clock_timestamp()
    """), {"id": verification_id, "collector": collector_uuid,
           "soldier_id": soldier_id, "error": error})
    if result.rowcount != 1:
        raise RuntimeError("verification lease expired or no longer owned")
