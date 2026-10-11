"""Explicit D2 soak ignition/stop transaction primitives; never automatic.

The worker must separately enforce the stored deadline before every HTTP
request. Stopping admission does not itself terminate remote workers.
"""
from __future__ import annotations
from datetime import timedelta
from sqlalchemy import text
from scripts.stage9c_three_hour_soak_ledger import (
    RUN_ID, BASELINE_EVENT, MAX_ATTEMPTS, SITE_ATTEMPTS,
    guard, digest_cohort,
)


def ignite(conn, ids):
    guard(conn)
    digest = digest_cohort(ids)
    conn.execute(text("SELECT pg_advisory_xact_lock(90841011,3)"))
    run = conn.execute(text("""
        SELECT cohort_digest,baseline_event_id,attempt_ceiling,
               site_attempt_ceiling,state,start_at,deadline_at
        FROM soak_runs WHERE run_id=:run FOR UPDATE
    """), {"run":RUN_ID}).one_or_none()
    if run is None or tuple(run) != (
        digest,BASELINE_EVENT,MAX_ATTEMPTS,SITE_ATTEMPTS,"prepared",None,None
    ):
        raise RuntimeError("run not exactly prepared; ignition refused")
    if conn.execute(text("SELECT count(*) FROM soak_rounds")).scalar_one():
        raise RuntimeError("round ledger already populated")
    if conn.execute(text("SELECT count(*) FROM collection_jobs")).scalar_one():
        raise RuntimeError("queue not empty")
    if conn.execute(text("SELECT coalesce(max(event_id),0) FROM collection_events")).scalar_one() != BASELINE_EVENT:
        raise RuntimeError("event baseline changed")
    started = conn.execute(text("SELECT clock_timestamp()")).scalar_one()
    deadline = started + timedelta(hours=3)
    conn.execute(text("""
        UPDATE soak_runs SET state='running',start_at=:start,
          deadline_at=:deadline,updated_at=clock_timestamp()
        WHERE run_id=:run AND state='prepared'
    """), {"run":RUN_ID,"start":started,"deadline":deadline})
    return {"run_id":RUN_ID,"start_at":started,"deadline_at":deadline}


def stop(conn, reason):
    guard(conn)
    if not reason or not reason.strip():
        raise ValueError("stop reason required")
    conn.execute(text("SELECT pg_advisory_xact_lock(90841011,3)"))
    run = conn.execute(text("""
        SELECT state FROM soak_runs WHERE run_id=:run FOR UPDATE
    """), {"run":RUN_ID}).one_or_none()
    if run is None:
        raise RuntimeError("run not found")
    if run.state in ("completed","failed","stopped"):
        return run.state
    conn.execute(text("""
        UPDATE soak_runs SET state='stopping',stop_reason=:reason,
          updated_at=clock_timestamp()
        WHERE run_id=:run
    """), {"run":RUN_ID,"reason":reason.strip()})
    return "stopping"


def http_allowed(conn, *, site):
    """Read-only deadline and per-site attempt check.

    NOT an atomic reservation. Must not be used as the sole attempt limiter;
    the worker must additionally implement a serialized site reservation
    before attempting HTTP.
    """
    guard(conn)
    if site not in ("tcou","kah-01","hnl-01"):
        raise RuntimeError("unrecognized site")
    run = conn.execute(text("""
        SELECT state,deadline_at FROM soak_runs WHERE run_id=:run
    """), {"run":RUN_ID}).one_or_none()
    if run is None or run.state != "running" or run.deadline_at is None:
        return False
    if conn.execute(text("SELECT clock_timestamp()")).scalar_one() >= run.deadline_at:
        return False
    used = conn.execute(text("""
        SELECT count(DISTINCT (job_id,attempt_number))
        FROM collection_events
        WHERE event_id>:base AND resource='detailed'
          AND event_type='collection_attempt_started'
          AND hostname_snapshot=:site
    """), {"base":BASELINE_EVENT,"site":site}).scalar_one()
    return used < SITE_ATTEMPTS
