"""Stage 9C read-only checkpoint evidence; never authorizes rollout.

Caller must explicitly begin a PostgreSQL READ ONLY transaction. This
module never mutates database state or issues external requests.
"""
from datetime import datetime, timedelta

from sqlalchemy import text

from bf4ps.production_hosts import RESOURCES
from bf4ps.stage9c_supervision import BOUNDARY_EVENT_ID, CUTOVER_AT, REVISION
from bf4ps.stage9c_checkpoint_math import observed_rolling_max

EXPECTED_DATABASE = "bf4_playerstats_test"
CEILING = 1296


def inspect_checkpoint(conn, run_id, *, expected_database=EXPECTED_DATABASE):
    db, rev, recovery, read_only = conn.execute(text("""
        SELECT current_database(),
               (SELECT version_num FROM alembic_version),
               pg_is_in_recovery(), current_setting('transaction_read_only')
    """)).one()
    if (db, rev, recovery, read_only) != (expected_database, REVISION, False, "on"):
        raise RuntimeError("refusing unsafe database/revision/read-only transaction")
    run = conn.execute(text("""
        SELECT state,cutover_at,since_event_id,started_at,deadline_at
        FROM stage9c_supervision_runs WHERE run_id=:run_id
    """), {"run_id": run_id}).mappings().one_or_none()
    if run is None or run["cutover_at"] != datetime.fromisoformat(CUTOVER_AT) or run["since_event_id"] != BOUNDARY_EVENT_ID:
        raise RuntimeError("missing run or wrong frozen boundary")
    start, deadline = run["started_at"], run["deadline_at"]
    if (start is None or deadline is None or start.tzinfo is None
            or deadline.tzinfo is None or deadline - start != timedelta(hours=6)):
        raise RuntimeError("invalid persisted supervision interval")
    now = conn.execute(text("SELECT transaction_timestamp()")).scalar_one()
    if now < start:
        raise RuntimeError("supervision has not started")
    rows = conn.execute(text("""
        SELECT event_id,occurred_at FROM collection_events
        WHERE occurred_at > :lookback AND occurred_at <= :now
          AND lane='background' AND event_type='collection_attempt_started'
          AND resource=ANY(:resources)
        ORDER BY occurred_at,event_id
    """), {"lookback": start - timedelta(hours=1),
           "now": now, "resources": list(RESOURCES)}).mappings().all()
    maximum = observed_rolling_max(
        [(row["event_id"], row["occurred_at"]) for row in rows],
        supervision_start=start, checkpoint_at=now,
    )
    return {"state": run["state"], "started_at": start,
            "checkpoint_at": now, "eligible_events": len(rows),
            "rolling_max": maximum, "ceiling": CEILING,
            "observed_budget_pass": maximum <= CEILING,
            "ledger_completeness_verified": False}
