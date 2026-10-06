"""Failure classification and atomic retry persistence for weapon collection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.engine import Connection

from bf4ps.battlelog_detailed import UnsupportedPlatformError
from bf4ps.battlelog_weapons import (
    WeaponStatsDecodeError,
    WeaponStatsHTTPError,
    WeaponStatsNormalizationError,
    WeaponStatsTransportError,
)
from bf4ps.collection_jobs import ClaimedJob


@dataclass(frozen=True)
class WeaponFailure:
    error_class: str
    message: str
    http_status: int | None = None


def classify_weapon_failure(exc: Exception) -> WeaponFailure:
    message = str(exc).strip() or exc.__class__.__name__
    if isinstance(exc, WeaponStatsHTTPError):
        if exc.status in (403, 429):
            return WeaponFailure("battlelog_throttle", message, exc.status)
        if 500 <= exc.status <= 599:
            return WeaponFailure("battlelog_http_5xx", message, exc.status)
        return WeaponFailure("battlelog_http", message, exc.status)
    if isinstance(exc, WeaponStatsTransportError):
        return WeaponFailure("battlelog_transport", message)
    if isinstance(exc, WeaponStatsDecodeError):
        return WeaponFailure("battlelog_decode", message)
    if isinstance(exc, WeaponStatsNormalizationError):
        return WeaponFailure("battlelog_normalization", message)
    if isinstance(exc, UnsupportedPlatformError):
        return WeaponFailure("bf4ps_unsupported_platform", message)
    return WeaponFailure("bf4ps_internal", message)


def persist_weapon_retry_failure(
    conn: Connection,
    *,
    job: ClaimedJob,
    failure: WeaponFailure,
    attempted_at: datetime,
    persona_id: int,
    platform: str,
    collector_name: str,
    hostname: str,
    egress_key: str,
    duration_ms: int,
    retry_after_seconds: int,
) -> None:
    """Atomically record a retryable weapon failure and release the owned job."""
    if job.resource != "weapons":
        raise ValueError("persist_weapon_retry_failure requires a weapons job")
    if duration_ms < 0:
        raise ValueError("duration_ms must be non-negative")
    if retry_after_seconds < 0:
        raise ValueError("retry_after_seconds must be non-negative")
    if failure.http_status is not None and not 100 <= failure.http_status <= 599:
        raise ValueError("http_status must be between 100 and 599")

    ownership = conn.execute(text("""
        SELECT 1 FROM collection_jobs
        WHERE job_id=:job_id AND soldier_id=:soldier_id AND resource='weapons'
          AND status='running' AND collector_uuid=:collector_uuid
          AND lease_token=:lease_token AND lease_expires_at > now()
        FOR UPDATE
    """), {"job_id": job.job_id, "soldier_id": job.soldier_id,
           "collector_uuid": job.collector_uuid, "lease_token": job.lease_token}).one_or_none()
    if ownership is None:
        raise RuntimeError("weapon failure rejected: job lease is no longer owned")

    conn.execute(text("""
        INSERT INTO collection_state
          (soldier_id, weapons_state, weapons_last_attempt_at, weapons_next_due_at,
           weapons_consecutive_failures, weapons_last_error_class,
           weapons_last_error_message, updated_at)
        VALUES (:soldier_id, 'temporary_failure', :attempted_at,
                :attempted_at + (:retry_after_seconds * interval '1 second'),
                1, :error_class, :error_message, now())
        ON CONFLICT (soldier_id) DO UPDATE SET
          weapons_state='temporary_failure',
          weapons_last_attempt_at=EXCLUDED.weapons_last_attempt_at,
          weapons_next_due_at=EXCLUDED.weapons_next_due_at,
          weapons_consecutive_failures=collection_state.weapons_consecutive_failures + 1,
          weapons_last_error_class=EXCLUDED.weapons_last_error_class,
          weapons_last_error_message=EXCLUDED.weapons_last_error_message,
          updated_at=now()
    """), {"soldier_id": job.soldier_id, "attempted_at": attempted_at,
           "retry_after_seconds": retry_after_seconds, "error_class": failure.error_class,
           "error_message": failure.message[:2000]})

    conn.execute(text("""
        INSERT INTO collection_events
          (collector_uuid, collector_name_snapshot, hostname_snapshot, egress_key_snapshot,
           job_id, soldier_id, persona_id, platform, resource, lane, event_type,
           attempt_number, result, duration_ms, http_status, error_class, error_message,
           lease_token, metadata)
        VALUES (:collector_uuid, :collector_name, :hostname, :egress_key,
                :job_id, :soldier_id, :persona_id, :platform, 'weapons', :lane,
                'collection_failure', :attempt_number, 'temporary_failure', :duration_ms,
                :http_status, :error_class, :error_message, :lease_token,
                jsonb_build_object('retry_after_seconds', :retry_after_seconds))
    """), {"collector_uuid": job.collector_uuid, "collector_name": collector_name,
           "hostname": hostname, "egress_key": egress_key, "job_id": job.job_id,
           "soldier_id": job.soldier_id, "persona_id": persona_id, "platform": platform,
           "lane": job.lane, "attempt_number": job.attempt_count, "duration_ms": duration_ms,
           "http_status": failure.http_status, "error_class": failure.error_class,
           "error_message": failure.message[:2000], "lease_token": job.lease_token,
           "retry_after_seconds": retry_after_seconds})

    released = conn.execute(text("""
        UPDATE collection_jobs SET
          status='pending', eligible_at=:attempted_at + (:retry_after_seconds * interval '1 second'),
          collector_uuid=NULL, lease_token=NULL, claimed_at=NULL, started_at=NULL,
          lease_expires_at=NULL, last_error_class=:error_class, last_error_at=:attempted_at,
          updated_at=now()
        WHERE job_id=:job_id AND soldier_id=:soldier_id AND resource='weapons'
          AND status='running' AND collector_uuid=:collector_uuid
          AND lease_token=:lease_token AND lease_expires_at > now()
    """), {"job_id": job.job_id, "soldier_id": job.soldier_id,
           "collector_uuid": job.collector_uuid, "lease_token": job.lease_token,
           "attempted_at": attempted_at, "retry_after_seconds": retry_after_seconds,
           "error_class": failure.error_class})
    if released.rowcount != 1:
        raise RuntimeError("weapon failure rejected during retry release: lease ownership lost")
