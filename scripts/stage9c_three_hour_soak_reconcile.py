"""Stage 9C D2 soak round reconciliation and operator read-only status.

Never infers success from an empty queue alone: every attributed job needs a
durable collection_success event. Failure or ambiguity requires operator action.
"""
from __future__ import annotations

import argparse
import json

from sqlalchemy import text
from scripts.stage9c_three_site_live_ignition import engine
from scripts.stage9c_three_hour_soak_ledger import RUN_ID, BASELINE_EVENT, guard


def inspect_round(conn, number: int):
    guard(conn)
    r = conn.execute(text("""
        SELECT state FROM soak_rounds
        WHERE run_id=:run AND round_number=:n
    """), {"run": RUN_ID, "n": number}).one_or_none()
    if r is None:
        raise RuntimeError("round not found")
    rows = conn.execute(text("""
        SELECT j.soldier_id,j.job_id,j.outcome,
          EXISTS(SELECT 1 FROM collection_jobs q WHERE q.job_id=j.job_id) AS queued,
          (SELECT count(*) FROM collection_events e
           WHERE e.event_id>:base AND e.job_id=j.job_id
             AND e.resource='detailed' AND e.event_type='collection_success') AS successes,
          (SELECT count(*) FROM collection_events e
           WHERE e.event_id>:base AND e.job_id=j.job_id
             AND e.resource='detailed' AND e.event_type='collection_attempt_started') AS starts
        FROM soak_round_jobs j
        WHERE j.run_id=:run AND j.round_number=:n
        ORDER BY j.soldier_id
    """), {"run": RUN_ID, "n": number, "base": BASELINE_EVENT}).mappings().all()
    if len(rows) != 9:
        raise RuntimeError("round attribution must contain exactly nine jobs")
    return {"round": number, "state": r.state,
            "jobs": [dict(x) for x in rows],
            "all_success": all(not x["queued"] and x["successes"] == 1 and x["starts"] >= 1 for x in rows),
            "any_queued": any(x["queued"] for x in rows),
            "anomalies": [x["job_id"] for x in rows if x["successes"] > 1 or
                          (not x["queued"] and x["successes"] == 0)]}


def reconcile(conn, number: int):
    """Reconcile under coordinator lock; caller controls transaction commit."""
    guard(conn)
    conn.execute(text("SELECT pg_advisory_xact_lock(90841011,3)"))
    run = conn.execute(text("""
        SELECT state FROM soak_runs WHERE run_id=:run FOR UPDATE
    """), {"run": RUN_ID}).one_or_none()
    if run is None or run.state not in ("running", "stopping"):
        raise RuntimeError("run not active")
    result = inspect_round(conn, number)
    if result["state"] == "completed":
        return result
    if result["state"] != "enqueued":
        raise RuntimeError("round not enqueued")
    if result["anomalies"]:
        raise RuntimeError(f"missing/duplicate success events: {result['anomalies']}")
    if not result["all_success"]:
        return result
    conn.execute(text("""
        UPDATE soak_round_jobs SET outcome='success'
        WHERE run_id=:run AND round_number=:n AND outcome='pending'
    """), {"run": RUN_ID, "n": number})
    conn.execute(text("""
        UPDATE soak_rounds SET state='completed',completed_at=clock_timestamp()
        WHERE run_id=:run AND round_number=:n AND state='enqueued'
    """), {"run": RUN_ID, "n": number})
    result["state"] = "completed"
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=["status"])
    p.add_argument("--round", type=int, required=True)
    args = p.parse_args()
    with engine().connect() as conn:
        print(json.dumps(inspect_round(conn, args.round), sort_keys=True, default=str))


if __name__ == "__main__":
    main()
