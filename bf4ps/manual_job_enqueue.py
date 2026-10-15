"""Insert absent manual collection jobs without changing existing leases."""
from sqlalchemy import text
from sqlalchemy.engine import Connection
from bf4ps.manual_request_policy import RESOURCES


def insert_missing_manual_jobs(conn: Connection, *, soldier_id: int, resources: tuple[str, ...]) -> tuple[str, ...]:
    if type(soldier_id) is not int or soldier_id <= 0:
        raise ValueError('invalid soldier ID')
    if len(resources) != len(set(resources)) or any(r not in RESOURCES for r in resources):
        raise ValueError('invalid resource selection')
    if not resources:
        return ()
    rows = conn.execute(text('''
        INSERT INTO collection_jobs
          (soldier_id, resource, lane, priority_class, reason,
           status, priority_value, eligible_at)
        SELECT :soldier_id, unnest(CAST(:resources AS text[])), 'background',
               'interactive', 'manual_request', 'pending', 100, now()
        ON CONFLICT (soldier_id, resource) DO NOTHING
        RETURNING resource
    '''), {'soldier_id': soldier_id, 'resources': list(resources)}).scalars().all()
    found = set(rows)
    return tuple(r for r in RESOURCES if r in found)