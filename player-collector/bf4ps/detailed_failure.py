"""Failure classification and atomic retry persistence for detailed collection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.engine import Connection

from bf4ps.battlelog_detailed import (
    DetailedStatsDecodeError,
    DetailedStatsHTTPError,
    DetailedStatsNormalizationError,
    DetailedStatsTransportError,
    UnsupportedPlatformError,
)
from bf4ps.collection_jobs import ClaimedJob


@dataclass(frozen=True)
class DetailedFailure:
    error_class: str
    message: str
    http_status: int | None = None


def classify_detailed_failure(exc: Exception) -> DetailedFailure:
    """Map a collection exception to the Phase 1 structured failure vocabulary.

    Phase 1 deliberately does not infer terminal/unavailable semantics from a
    generic HTTP response. Until Battlelog not-found behavior is established
    live, HTTP failures remain retryable and preserve last-known-good state.

    HTTP 403 and 429 are both explicit throttle signals.  Keeping them under
    one durable error class makes Phase 3 distributed-runtime evidence easy to
    identify while preserving the exact HTTP status in collection_events.
    """
    message = str(exc).strip() or exc.__class__.__name__
    if isinstance(exc, DetailedStatsHTTPError):
        if exc.status in (403, 429):
            return DetailedFailure("battlelog_throttle", message, exc.status)
        if 500 <= exc.status <= 599:
            return DetailedFailure("battlelog_http_5xx", message, exc.status)
        return DetailedFailure("battlelog_http", message, exc.status)
    if isinstance(exc, DetailedStatsTransportError):
        return DetailedFailure("battlelog_transport", message)
    if isinstance(exc, DetailedStatsDecodeError):
        return DetailedFailure("battlelog_decode", message)
    if isinstance(exc, DetailedStatsNormalizationError):
        return DetailedFailure("battlelog_normalization", message)
    if isinstance(exc, UnsupportedPlatformError):
        return DetailedFailure("bf4ps_unsupported_platform", message)
    return DetailedFailure("bf4ps_internal", message)


def persist_detailed_retry_failure(
    conn: Connection,
    *,
    job: ClaimedJob,
    failure: DetailedFailure,
    attempted_at: datetime,
    persona_id: int,
    platform: str,
    collector_name: str,
    hostname: str,
    egress_key: str,
    duration_ms: int,
    retry_after_seconds: int,
) -> None:
    """Atomically record a retryable failure and release the owned job.

    This function intentionally never writes detailed_stats_current or
    detailed_stats_history. The caller owns the transaction; state, event, and
    queue release therefore commit together or roll back together.
    """
    if job.resource != "detailed":
        raise ValueError("persist_detailed_retry_failure requires a detailed job")
    if duration_ms < 0:
        raise ValueError("duration_ms must be non-negative")
    if retry_after_seconds < 0:
        raise ValueError("retry_after_seconds must be non-negative")
    if failure.http_status is not None and not 100 <= failure.http_status <= 599:
        raise ValueError("http_status must be between 100 and 599")

    ownership = conn.execute(
        text(
            """
            SELECT 1
            FROM collection_jobs
            WHERE job_id = :job_id
              AND soldier_id = :soldier_id
              AND resource = 'detailed'
              AND status = 'running'
              AND collector_uuid = :collector_uuid
              AND lease_token = :lease_token
              AND lease_expires_at > now()
            FOR UPDATE
            """
        ),
        {
            "job_id": job.job_id,
            "soldier_id": job.soldier_id,
            "collector_uuid": job.collector_uuid,
            "lease_token": job.lease_token,
        },
    ).one_or_none()
    if ownership is None:
        raise RuntimeError("detailed failure rejected: job lease is no longer owned")

    conn.execute(
        text(
            """
            INSERT INTO collection_state
                (soldier_id, detailed_state, detailed_last_attempt_at,
                 detailed_next_due_at, detailed_consecutive_failures,
                 detailed_last_error_class, detailed_last_error_message, updated_at)
            VALUES
                (:soldier_id, 'temporary_failure', :attempted_at,
                 :attempted_at + (:retry_after_seconds * interval '1 second'),
                 1, :error_class, :error_message, now())
            ON CONFLICT (soldier_id) DO UPDATE
            SET detailed_state = 'temporary_failure',
                detailed_last_attempt_at = EXCLUDED.detailed_last_attempt_at,
                detailed_next_due_at = EXCLUDED.detailed_next_due_at,
                detailed_consecutive_failures = collection_state.detailed_consecutive_failures + 1,
                detailed_last_error_class = EXCLUDED.detailed_last_error_class,
                detailed_last_error_message = EXCLUDED.detailed_last_error_message,
                updated_at = now()
            """
        ),
        {
            "soldier_id": job.soldier_id,
            "attempted_at": attempted_at,
            "retry_after_seconds": retry_after_seconds,
            "error_class": failure.error_class,
            "error_message": failure.message[:2000],
        },
    )

    conn.execute(
        text(
            """
            INSERT INTO collection_events
                (collector_uuid, collector_name_snapshot, hostname_snapshot,
                 egress_key_snapshot, job_id, soldier_id, persona_id, platform,
                 resource, lane, event_type, attempt_number, result,
                 duration_ms, http_status, error_class, error_message,
                 lease_token, metadata)
            VALUES
                (:collector_uuid, :collector_name, :hostname, :egress_key,
                 :job_id, :soldier_id, :persona_id, :platform,
                 'detailed', :lane, 'collection_failure', :attempt_number,
                 'temporary_failure', :duration_ms, :http_status, :error_class,
                 :error_message, :lease_token, CAST(:metadata AS jsonb))
            """
        ),
        {
            "collector_uuid": job.collector_uuid,
            "collector_name": collector_name,
            "hostname": hostname,
            "egress_key": egress_key,
            "job_id": job.job_id,
            "soldier_id": job.soldier_id,
            "persona_id": persona_id,
            "platform": platform,
            "lane": job.lane,
            "attempt_number": job.attempt_count,
            "duration_ms": duration_ms,
            "http_status": failure.http_status,
            "error_class": failure.error_class,
            "error_message": failure.message[:2000],
            "lease_token": job.lease_token,
            "metadata": '{"retry_after_seconds": ' + str(retry_after_seconds) + "}",
        },
    )

    released = conn.execute(
        text(
            """
            UPDATE collection_jobs
            SET status = 'pending',
                eligible_at = :attempted_at + (:retry_after_seconds * interval '1 second'),
                collector_uuid = NULL,
                lease_token = NULL,
                claimed_at = NULL,
                started_at = NULL,
                lease_expires_at = NULL,
                last_error_class = :error_class,
                last_error_at = :attempted_at,
                updated_at = now()
            WHERE job_id = :job_id
              AND soldier_id = :soldier_id
              AND resource = 'detailed'
              AND status = 'running'
              AND collector_uuid = :collector_uuid
              AND lease_token = :lease_token
              AND lease_expires_at > now()
            """
        ),
        {
            "job_id": job.job_id,
            "soldier_id": job.soldier_id,
            "collector_uuid": job.collector_uuid,
            "lease_token": job.lease_token,
            "attempted_at": attempted_at,
            "retry_after_seconds": retry_after_seconds,
            "error_class": failure.error_class,
        },
    )
    if released.rowcount != 1:
        raise RuntimeError("detailed failure rejected during retry release: lease ownership lost")
