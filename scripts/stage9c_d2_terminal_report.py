"""Read-only terminal evidence report for the isolated Stage 9C D2 soak.

Never mutates the queue, run state, rounds, or HTTP event ledger.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone

from sqlalchemy import text

from scripts.stage9c_three_site_live_ignition import engine
from scripts.stage9c_three_hour_soak_ledger import RUN_ID, BASELINE_EVENT, ROUNDS, guard


def classify_job(row, now):
    """Classify durable evidence, without inferring unrecorded HTTP success."""
    starts = int(row["starts"])
    successes = int(row["successes"])
    queued = bool(row["queued"])
    status = row["queue_status"]
    lease = row["lease_expires_at"]
    if successes > 1 or starts > 1 or successes > starts:
        return "anomalous_events"
    if successes == 1 and starts == 1 and not queued:
        return "durable_success"
    if starts > 0 and successes == 0:
        return "physical_start_without_success"
    if starts == 1 and successes == 1 and queued:
        return "success_but_still_queued"
    if starts == 0 and successes == 0 and queued:
        if status == "running":
            return "expired_running_lease" if lease is not None and lease <= now else "running_without_physical_start"
        if status == "pending":
            return "pending_without_physical_start"
        return "queued_other_status"
    return "unresolved_inconsistent"


def inspect_terminal(conn, *, now=None):
    guard(conn)
    run = conn.execute(text("""
        SELECT run_id,state,stop_reason,start_at,deadline_at,
               baseline_event_id,attempt_ceiling,site_attempt_ceiling
        FROM soak_runs WHERE run_id=:run
    """), {"run": RUN_ID}).mappings().one_or_none()
    if run is None:
        raise RuntimeError("SOAK BLOCK: historical run missing")
    if int(run["baseline_event_id"]) != BASELINE_EVENT:
        raise RuntimeError("SOAK BLOCK: unexpected event baseline")
    observed_at = now if now is not None else conn.execute(text("SELECT clock_timestamp()")).scalar_one()
    rounds = conn.execute(text("""
        SELECT round_number,state FROM soak_rounds
        WHERE run_id=:run ORDER BY round_number
    """), {"run": RUN_ID}).mappings().all()
    rows = conn.execute(text("""
        SELECT j.round_number,j.job_id,j.soldier_id,j.outcome,
               q.status AS queue_status,q.lease_expires_at,
               (q.job_id IS NOT NULL) AS queued,
               count(e.event_id) FILTER (WHERE e.event_type='collection_attempt_started') AS starts,
               count(e.event_id) FILTER (WHERE e.event_type='collection_success') AS successes
        FROM soak_round_jobs j
        LEFT JOIN collection_jobs q ON q.job_id=j.job_id
        LEFT JOIN collection_events e ON e.job_id=j.job_id
          AND e.event_id>:base AND e.resource='detailed'
          AND e.event_type IN ('collection_attempt_started','collection_success')
        WHERE j.run_id=:run
        GROUP BY j.round_number,j.job_id,j.soldier_id,j.outcome,
                 q.job_id,q.status,q.lease_expires_at
        ORDER BY j.round_number,j.soldier_id
    """), {"run": RUN_ID, "base": BASELINE_EVENT}).mappings().all()
    classified = [{**dict(row), "classification": classify_job(row, observed_at)} for row in rows]
    totals = dict(sorted(Counter(row["classification"] for row in classified).items()))
    discrepancies = [
        {"round_number": row["round_number"], "job_id": row["job_id"],
         "outcome": row["outcome"], "classification": row["classification"]}
        for row in classified
        if (row["classification"] == "durable_success" and row["outcome"] != "success")
        or (row["outcome"] == "success" and row["classification"] != "durable_success")
    ]
    return {
        "run": dict(run), "observed_at": observed_at,
        "rounds": [dict(r) for r in rounds],
        "classification_counts": totals, "outcome_discrepancies": discrepancies, "jobs": classified,
        "complete": (run["state"] == "completed" and len(rounds) == ROUNDS
                     and [r["round_number"] for r in rounds] == list(range(1, ROUNDS + 1))
                     and all(r["state"] == "completed" for r in rounds)
                     and len(classified) == ROUNDS * 9
                     and totals == {"durable_success": ROUNDS * 9}
                     and not discrepancies
                     and all(row["outcome"] == "success" for row in classified)),
        "read_only": True,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("report",))
    args = parser.parse_args()
    db = engine()
    try:
        with db.connect() as conn:
            print(json.dumps(inspect_terminal(conn), default=str, sort_keys=True))
    finally:
        db.dispose()


if __name__ == "__main__":
    main()
