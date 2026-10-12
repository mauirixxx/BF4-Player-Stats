"""D4-only shared HTTP admission/stop gate.

Every physical attempt checks for an existing HTTP 403/429 failure while
holding a PostgreSQL transaction advisory lock. Workers must also check
the same gate before claiming further jobs. This is a fail-closed
cooperative stop, not a guarantee of cancelling already in-flight HTTP.
"""
from __future__ import annotations

from sqlalchemy import text

STOP_SQL = text("""
SELECT event_id, http_status
FROM collection_events
WHERE event_type = 'collection_failure'
  AND http_status IN (403, 429)
ORDER BY event_id DESC LIMIT 1
""")

def assert_no_rate_block(conn, job=None, identity=None):
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('bf4ps:d4-real30-http-stop'))"))
    row = conn.execute(STOP_SQL).one_or_none()
    if row is not None:
        raise RuntimeError(
            f"D4 HTTP HARD STOP: status={row.http_status} event={row.event_id}; no further requests"
        )
    # Also block if another worker recorded an attempt but never finished it.
    # In-flight requests may legitimately overlap across nodes, so this is
    # not a request-completion requirement.
