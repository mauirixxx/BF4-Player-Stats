"""Atomic manual request acceptance and safe promotion for registered soldiers.

Feature remains disabled in production. The caller must use `engine.begin()`;
this function does not commit or make an HTTP request.
"""
from dataclasses import dataclass
from sqlalchemy import text
from sqlalchemy.engine import Connection

from bf4ps.manual_request_ledger import accept_existing_soldier_request
from bf4ps.manual_request_policy import RESOURCES, refreshable_resources
from bf4ps.manual_job_priority import promote_existing_pending_jobs


@dataclass(frozen=True)
class ManualAdmission:
    accepted: bool
    request_id: int | None
    retry_after_seconds: int
    resources_needed: tuple[str, ...]
    promoted: tuple[str, ...]


def admit_registered_soldier(conn: Connection, *, soldier_id: int, kind: str = 'refresh') -> ManualAdmission:
    """Accept a request and promote only safely eligible pre-existing jobs.

    An accepted request is *not* a promise of collection: resources without a
    pending job, leased jobs and backoff jobs need follow-up scheduler handling.
    """
    accepted = accept_existing_soldier_request(conn, soldier_id=soldier_id, kind=kind)
    if not accepted.accepted:
        return ManualAdmission(False, accepted.request_id, accepted.retry_after_seconds, (), ())
    state = conn.execute(text('''
        SELECT detailed_last_success_at, weapons_last_success_at,
               vehicles_last_success_at, profile_last_success_at
        FROM collection_state WHERE soldier_id = :soldier_id
    '''), {'soldier_id': soldier_id}).mappings().one_or_none()
    now = conn.execute(text('SELECT clock_timestamp()')).scalar_one()
    stamps = {resource: (state[f'{resource}_last_success_at'] if state is not None else None) for resource in RESOURCES}
    needed = refreshable_resources(last_success=stamps, now=now)
    promoted = promote_existing_pending_jobs(conn, soldier_id=soldier_id, resources=needed)
    # Never report queued unless all required resources have actionable work.
    # The ledger remains 'accepted' until a separately implemented scheduler
    # and status reconciler confirm progress.
    return ManualAdmission(True, accepted.request_id, 0, needed, promoted)