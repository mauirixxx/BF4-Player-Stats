"""Read-only event metrics for distributed BF4PS collectors.

Queries target the documented collection_events schema (migration 0001).
No DB connections or writes are performed by this module.
"""
from __future__ import annotations

from sqlalchemy import text


DUPLICATE_AND_FAILURE_COUNTS_SQL = text("""
    SELECT date_trunc('hour', occurred_at) AS hour_utc,
           COALESCE(hostname_snapshot, '<unknown>') AS hostname,
           COALESCE(egress_key_snapshot, '<unknown>') AS egress_key,
           COALESCE(resource, '<unknown>') AS resource,
           COUNT(*) FILTER (
               WHERE event_type = 'collection_duplicate_discarded'
           ) AS duplicate_discards,
           COUNT(*) FILTER (
               WHERE event_type = 'collection_failure'
           ) AS failures,
           COUNT(*) FILTER (
               WHERE event_type = 'collection_success'
           ) AS successes,
           COUNT(*) FILTER (
               WHERE event_type = 'collection_failure'
                 AND http_status IN (403, 429)
           ) AS throttle_failures
    FROM collection_events
    WHERE occurred_at >= :since
      AND occurred_at < :until
      AND event_type IN (
          'collection_duplicate_discarded',
          'collection_failure',
          'collection_success'
      )
    GROUP BY 1, 2, 3, 4
    ORDER BY hour_utc, hostname, egress_key, resource
""")
