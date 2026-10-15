"""Transactional, inert manual request acceptance for an *existing* soldier.

This module does not enqueue or reprioritize collector jobs. It must only be
called by a trusted backend transaction, never directly by a browser role.
"""
from dataclasses import dataclass
from datetime import timedelta
from sqlalchemy import text
from sqlalchemy.engine import Connection

COOLDOWN_SECONDS = 3600


@dataclass(frozen=True)
class Acceptance:
    accepted: bool
    request_id: int | None
    retry_after_seconds: int


def accept_existing_soldier_request(conn: Connection, *, soldier_id: int, kind: str) -> Acceptance:
    """Serialize requests for one soldier; caller owns transaction commit/rollback.

    Lock the existing soldier row, not the optional cooldown row: that also
    serializes concurrent *first* requests where no cooldown row exists yet.
    All timestamps come from PostgreSQL after the lock is acquired.
    """
    if not isinstance(soldier_id, int) or isinstance(soldier_id, bool) or soldier_id <= 0:
        raise ValueError('invalid soldier ID')
    if kind not in ('add', 'refresh'):
        raise ValueError('invalid request kind')
    found = conn.execute(text('SELECT soldier_id FROM soldiers WHERE soldier_id = :id FOR UPDATE'), {'id': soldier_id}).scalar_one_or_none()
    if found is None:
        raise ValueError('soldier not registered')
    now = conn.execute(text('SELECT clock_timestamp()')).scalar_one()
    row = conn.execute(text('''
        SELECT last_accepted_at, last_request_id FROM manual_request_cooldowns
        WHERE soldier_id = :id FOR UPDATE
    '''), {'id': soldier_id}).one_or_none()
    if row is not None:
        seconds = (row.last_accepted_at + timedelta(seconds=COOLDOWN_SECONDS) - now).total_seconds()
        if seconds > 0:
            return Acceptance(False, int(row.last_request_id), max(1, int(-(-seconds // 1))))
    request_id = conn.execute(text('''
        INSERT INTO manual_collection_requests (soldier_id, request_kind, status, requested_at)
        VALUES (:id, :kind, 'accepted', :now) RETURNING request_id
    '''), {'id': soldier_id, 'kind': kind, 'now': now}).scalar_one()
    conn.execute(text('''
        INSERT INTO manual_request_cooldowns (soldier_id, last_accepted_at, last_request_id)
        VALUES (:id, :now, :request_id)
        ON CONFLICT (soldier_id) DO UPDATE
        SET last_accepted_at = EXCLUDED.last_accepted_at,
            last_request_id = EXCLUDED.last_request_id
    '''), {'id': soldier_id, 'now': now, 'request_id': request_id})
    return Acceptance(True, int(request_id), 0)