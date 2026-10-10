"""Read-only PostgreSQL D2 three-source usage query (no collector wiring).

Caller must acquire the existing background advisory transaction lock and
sample PostgreSQL clock_timestamp() AFTER locking. This function itself does
not authorize admission. It is designed for isolated scratch validation.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import text
from sqlalchemy.engine import Connection


USAGE_SQL = text("""
WITH evidence AS (
    SELECT 'started'::text AS source, job_id, attempt_number, resource,
           lease_token, occurred_at AS observed_at
    FROM collection_events
    WHERE lane = 'background'
      AND event_type = 'collection_attempt_started'
      AND occurred_at > :at - interval '1 hour'
      AND occurred_at <= :at
    UNION ALL
    SELECT 'reserved'::text, job_id, attempt_count, resource,
           lease_token, claimed_at
    FROM collection_jobs
    WHERE lane = 'background'
      AND status IN ('claimed', 'running')
      AND lease_expires_at > :at
    UNION ALL
    SELECT 'dispatch'::text, job_id, attempt_number, resource,
           lease_token, admitted_at
    FROM outbound_dispatches
    WHERE lane = 'background'
      AND admitted_at > :at - interval '1 hour'
      AND admitted_at <= :at
),
complete AS (
    SELECT source, job_id, attempt_number, resource, lease_token
    FROM evidence
    WHERE job_id IS NOT NULL AND attempt_number IS NOT NULL
      AND resource IS NOT NULL AND lease_token IS NOT NULL
),
groups AS (
    SELECT job_id, attempt_number, resource, lease_token,
           COUNT(*) FILTER (WHERE source = 'started') AS starts
    FROM complete
    GROUP BY job_id, attempt_number, resource, lease_token
)
SELECT
    (SELECT COUNT(*) FROM groups)
    + (SELECT COUNT(*) FROM evidence WHERE job_id IS NULL
        OR attempt_number IS NULL OR resource IS NULL OR lease_token IS NULL)
    + COALESCE((SELECT SUM(GREATEST(starts - 1, 0)) FROM groups), 0)
    AS conservative_usage
""")


def read_conservative_background_usage(conn: Connection, *, at: datetime) -> int:
    """Compute a conservative evidence count; does NOT grant a send permit."""
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("at must be timezone-aware")
    return int(conn.execute(USAGE_SQL, {"at": at}).scalar_one())
