"""Lease-safe promotion of existing manual-request collection jobs.

Only changes eligible, non-retry pending jobs. This does not alter admission
fairness or collector code; that requires a separately tested rollout.
"""
from sqlalchemy import text
from sqlalchemy.engine import Connection
from bf4ps.manual_request_policy import RESOURCES


def promote_existing_pending_jobs(conn: Connection, *, soldier_id: int, resources: tuple[str, ...]) -> tuple[str, ...]:
    """Promote pending work without touching leased jobs or retry backoff.

    A missing job is deliberately not created by this helper. Admission must
    first verify identity, freshness and request cooldown transactionally.
    """
    if not isinstance(soldier_id, int) or isinstance(soldier_id, bool) or soldier_id <= 0:
        raise ValueError('invalid soldier ID')
    if len(set(resources)) != len(resources) or any(r not in RESOURCES for r in resources):
        raise ValueError('invalid resource selection')
    if not resources:
        return ()
    rows = conn.execute(text('''
        UPDATE collection_jobs
        SET priority_class = 'interactive',
            priority_value = GREATEST(priority_value, 100),
            reason = 'manual_refresh',
            updated_at = now()
        WHERE soldier_id = :soldier_id
          AND resource = ANY(:resources)
          AND lane = 'background'
          AND status = 'pending'
          AND last_error_at IS NULL
          AND eligible_at <= now()
        RETURNING resource
    '''), {'soldier_id': soldier_id, 'resources': list(resources)}).scalars().all()
    return tuple(r for r in RESOURCES if r in set(rows))