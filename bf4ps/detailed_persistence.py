"""Atomic persistence for successful BF4 detailed-statistics collection."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Mapping

from sqlalchemy import text
from sqlalchemy.engine import Connection

from bf4ps.battlelog_detailed import DECIMAL_FIELDS, INTEGER_FIELDS
from bf4ps.collection_jobs import ClaimedJob

DETAILED_FIELDS = tuple(INTEGER_FIELDS) + tuple(DECIMAL_FIELDS)


def _validate_stats(stats: Mapping[str, int | Decimal | None]) -> None:
    expected = set(DETAILED_FIELDS)
    observed = set(stats)
    missing = expected - observed
    extra = observed - expected
    if missing or extra:
        parts: list[str] = []
        if missing:
            parts.append(f"missing fields: {', '.join(sorted(missing))}")
        if extra:
            parts.append(f"unexpected fields: {', '.join(sorted(extra))}")
        raise ValueError("invalid detailed-stat field set (" + "; ".join(parts) + ")")


def persist_detailed_success(
    conn: Connection,
    *,
    job: ClaimedJob,
    stats: Mapping[str, int | Decimal | None],
    source_fetched_at: datetime,
    persona_id: int,
    platform: str,
    collector_name: str,
    hostname: str,
    egress_key: str,
    duration_ms: int,
    http_status: int = 200,
) -> bool:
    """Persist one successful detailed fetch and finalize its owned queue job.

    The caller supplies a transaction-owning Connection.  Every write below is
    deliberately performed through that same connection so current state,
    history, collection state, event, and queue finalization commit together.

    Returns True when a history snapshot was appended, False when the retained
    statistics were unchanged.  Loss/expiry of the fencing lease raises rather
    than permitting a partial/stale success commit.
    """
    if job.resource != "detailed":
        raise ValueError("persist_detailed_success requires a detailed job")
    if duration_ms < 0:
        raise ValueError("duration_ms must be non-negative")
    if not 100 <= http_status <= 599:
        raise ValueError("http_status must be between 100 and 599")
    _validate_stats(stats)

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
        raise RuntimeError("detailed success rejected: job lease is no longer owned")

    bind = {"soldier_id": job.soldier_id, "source_fetched_at": source_fetched_at, **stats}
    field_list = ", ".join(DETAILED_FIELDS)
    value_list = ", ".join(f":{field}" for field in DETAILED_FIELDS)
    update_list = ", ".join(f"{field} = EXCLUDED.{field}" for field in DETAILED_FIELDS)

    previous = conn.execute(
        text(
            f"""
            SELECT {field_list}
            FROM detailed_stats_history
            WHERE soldier_id = :soldier_id
            ORDER BY observed_at DESC, snapshot_id DESC
            LIMIT 1
            """
        ),
        {"soldier_id": job.soldier_id},
    ).mappings().one_or_none()

    changed = previous is None or any(previous[field] != stats[field] for field in DETAILED_FIELDS)
    if changed:
        conn.execute(
            text(
                f"""
                INSERT INTO detailed_stats_history
                    (soldier_id, {field_list}, observed_at)
                VALUES
                    (:soldier_id, {value_list}, :source_fetched_at)
                """
            ),
            bind,
        )

    conn.execute(
        text(
            f"""
            INSERT INTO detailed_stats_current
                (soldier_id, {field_list}, source_fetched_at, updated_at)
            VALUES
                (:soldier_id, {value_list}, :source_fetched_at, now())
            ON CONFLICT (soldier_id) DO UPDATE
            SET {update_list},
                source_fetched_at = EXCLUDED.source_fetched_at,
                updated_at = now()
            """
        ),
        bind,
    )

    conn.execute(
        text(
            """
            INSERT INTO collection_state
                (soldier_id, detailed_state, detailed_last_attempt_at,
                 detailed_last_success_at, detailed_next_due_at,
                 detailed_consecutive_failures, detailed_last_error_class,
                 detailed_last_error_message, updated_at)
            VALUES
                (:soldier_id, 'success', :source_fetched_at,
                 :source_fetched_at, NULL, 0, NULL, NULL, now())
            ON CONFLICT (soldier_id) DO UPDATE
            SET detailed_state = 'success',
                detailed_last_attempt_at = EXCLUDED.detailed_last_attempt_at,
                detailed_last_success_at = EXCLUDED.detailed_last_success_at,
                detailed_next_due_at = NULL,
                detailed_consecutive_failures = 0,
                detailed_last_error_class = NULL,
                detailed_last_error_message = NULL,
                updated_at = now()
            """
        ),
        {"soldier_id": job.soldier_id, "source_fetched_at": source_fetched_at},
    )

    conn.execute(
        text(
            """
            INSERT INTO collection_events
                (collector_uuid, collector_name_snapshot, hostname_snapshot,
                 egress_key_snapshot, job_id, soldier_id, persona_id, platform,
                 resource, lane, event_type, attempt_number, result,
                 duration_ms, http_status, lease_token, metadata)
            VALUES
                (:collector_uuid, :collector_name, :hostname, :egress_key,
                 :job_id, :soldier_id, :persona_id, :platform,
                 'detailed', :lane, 'collection_success', :attempt_number,
                 'success', :duration_ms, :http_status, :lease_token,
                 CAST(:metadata AS jsonb))
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
            "http_status": http_status,
            "lease_token": job.lease_token,
            "metadata": '{"history_appended": ' + ("true" if changed else "false") + "}",
        },
    )

    finalized = conn.execute(
        text(
            """
            DELETE FROM collection_jobs
            WHERE job_id = :job_id
              AND collector_uuid = :collector_uuid
              AND lease_token = :lease_token
              AND status = 'running'
              AND lease_expires_at > now()
            """
        ),
        {
            "job_id": job.job_id,
            "collector_uuid": job.collector_uuid,
            "lease_token": job.lease_token,
        },
    )
    if finalized.rowcount != 1:
        raise RuntimeError("detailed success rejected during finalization: lease ownership lost")

    return changed
