"""Read-only manual request status derived from durable collection evidence."""
from dataclasses import dataclass
from sqlalchemy import text
from sqlalchemy.engine import Connection


@dataclass(frozen=True)
class ManualStatus:
    request_id: int
    state: str
    resources_pending: int
    resources_running: int
    resources_retrying: int


def get_manual_request_status(conn: Connection, request_id: int) -> ManualStatus | None:
    if type(request_id) is not int or request_id <= 0:
        raise ValueError('invalid request ID')
    row = conn.execute(text('''
        SELECT r.request_id, r.status, r.requested_at,
               COUNT(j.job_id) FILTER (WHERE j.status = 'pending'
                   AND j.last_error_at IS NULL) AS pending,
               COUNT(j.job_id) FILTER (WHERE j.status IN ('claimed','running')) AS running,
               COUNT(j.job_id) FILTER (WHERE j.status = 'pending'
                   AND j.last_error_at IS NOT NULL) AS retrying
        FROM manual_collection_requests AS r
        LEFT JOIN collection_jobs AS j ON j.soldier_id = r.soldier_id
        WHERE r.request_id = :request_id
        GROUP BY r.request_id, r.status, r.requested_at
    '''), {'request_id': request_id}).mappings().one_or_none()
    if row is None:
        return None
    running = int(row['running'])
    retrying = int(row['retrying'])
    pending = int(row['pending'])
    # Do not infer completion from an empty queue: a worker may have removed
    # work, and collection success must be reconciled from event evidence.
    state = ('collecting' if running else 'retrying' if retrying else
             'queued' if pending else str(row['status']))
    return ManualStatus(int(row['request_id']), state, pending, running, retrying)