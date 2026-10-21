"""Stage 9C transactional lease primitives. No launcher or network requests.

Callers MUST verify the database identity, Alembic 0004, frozen boundary,
and independent safety inspection before invoking these operations.
These functions do not start collectors or activate a prepared run.
"""
from __future__ import annotations

from uuid import UUID
from sqlalchemy import text

REVISION = "0004_stage9c_supervision_runs"
CUTOVER_AT = "2026-10-08T00:47:34.757784+00:00"
BOUNDARY_EVENT_ID = 11558
LEASE_SECONDS = 20

GUARD_SQL = text("""
SELECT state, cutover_at, since_event_id, started_at, deadline_at,
       watchdog_owner, watchdog_generation, heartbeat_at, lease_expires_at,
       clock_timestamp() AS db_now
FROM stage9c_supervision_runs WHERE run_id=:run_id
""")

RENEW_SQL = text("""
UPDATE stage9c_supervision_runs
SET heartbeat_at=clock_timestamp(),
    lease_expires_at=clock_timestamp() + make_interval(secs => :ttl),
    updated_at=clock_timestamp()
WHERE run_id=:run_id AND state='active'
  AND watchdog_owner=:owner AND watchdog_generation=:generation
  AND cutover_at=CAST(:cutover AS timestamptz)
  AND since_event_id=:boundary
  AND lease_expires_at > clock_timestamp()
  AND deadline_at > clock_timestamp()
RETURNING lease_expires_at
""")

ABORT_SQL = text("""
UPDATE stage9c_supervision_runs
SET state='aborted', abort_at=clock_timestamp(),
    abort_reason=:reason, updated_at=clock_timestamp()
WHERE run_id=:run_id AND state='active'
  AND watchdog_owner=:owner AND watchdog_generation=:generation
  AND cutover_at=CAST(:cutover AS timestamptz)
  AND since_event_id=:boundary
RETURNING run_id
""")


class SupervisionRefused(RuntimeError):
    """Fail-closed: missing, stale, wrong, or terminal run."""


def _id(value):
    return UUID(str(value))


def _params(run_id, owner, generation):
    if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
        raise SupervisionRefused("invalid watchdog generation")
    return {"run_id": _id(run_id), "owner": _id(owner),
            "generation": generation, "cutover": CUTOVER_AT,
            "boundary": BOUNDARY_EVENT_ID}


def require_guard_lease(conn, run_id):
    """Read-only authorization check, using the database clock."""
    row = conn.execute(GUARD_SQL, {"run_id": _id(run_id)}).mappings().one_or_none()
    if row is None:
        raise SupervisionRefused("run missing")
    from datetime import datetime
    expected = datetime.fromisoformat(CUTOVER_AT)
    if (row["state"] != "active" or row["cutover_at"] != expected
            or row["since_event_id"] != BOUNDARY_EVENT_ID
            or row["started_at"] is None or row["deadline_at"] is None
            or row["watchdog_owner"] is None or row["watchdog_generation"] < 1
            or row["heartbeat_at"] is None or row["lease_expires_at"] is None
            or row["lease_expires_at"] <= row["db_now"]
            or row["deadline_at"] <= row["db_now"]):
        raise SupervisionRefused("run inactive, wrong boundary, expired or invalid")
    return row


def renew_after_inspection(conn, *, run_id, owner, generation, inspection_passed):
    """Caller owns transaction; never renew if safety inspection failed.

    Caller must commit the transaction; a rolled-back renewal grants nothing.
    """
    if inspection_passed is not True:
        raise SupervisionRefused("independent inspection did not pass")
    params = _params(run_id, owner, generation)
    params["ttl"] = LEASE_SECONDS
    row = conn.execute(RENEW_SQL, params).one_or_none()
    if row is None:
        raise SupervisionRefused("lease expired, fenced, terminal or wrong boundary")
    return row[0]


def abort_owned_run(conn, *, run_id, owner, generation, reason):
    """Sticky active→aborted transition. Caller must commit.

    This does NOT drain collectors: caller must perform fleet drain in the
    same transaction, and host-local guards must stop physical processes.
    """
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("abort reason required")
    row = conn.execute(ABORT_SQL, {**_params(run_id, owner, generation),
                                   "reason": reason.strip()}).one_or_none()
    if row is None:
        raise SupervisionRefused("abort refused: wrong owner or non-active run")
    return row[0]
