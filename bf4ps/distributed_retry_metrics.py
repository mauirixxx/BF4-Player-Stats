"""Read-only queue fairness metrics for the eight-egress collector fleet.

The queue intentionally puts fresh jobs before eligible retries within a
priority class. Operators must be able to detect retry starvation.
"""
from sqlalchemy import text

RETRY_FAIRNESS_SQL = text("""
    SELECT
        lane,
        resource,
        priority_class,
        COUNT(*) FILTER (
            WHERE status = 'pending'
              AND last_error_at IS NULL
              AND eligible_at <= :observed_at
        ) AS fresh_eligible,
        COUNT(*) FILTER (
            WHERE status = 'pending'
              AND last_error_at IS NOT NULL
              AND eligible_at <= :observed_at
        ) AS retries_eligible,
        COUNT(*) FILTER (
            WHERE status = 'pending'
              AND last_error_at IS NOT NULL
              AND eligible_at > :observed_at
        ) AS retries_waiting,
        MIN(eligible_at) FILTER (
            WHERE status = 'pending'
              AND last_error_at IS NOT NULL
              AND eligible_at <= :observed_at
        ) AS oldest_eligible_retry_at,
        MAX(EXTRACT(EPOCH FROM (:observed_at - eligible_at))) FILTER (
            WHERE status = 'pending'
              AND last_error_at IS NOT NULL
              AND eligible_at <= :observed_at
        ) AS oldest_retry_wait_seconds
    FROM collection_jobs
    GROUP BY lane, resource, priority_class
    ORDER BY lane, resource, priority_class
""")
