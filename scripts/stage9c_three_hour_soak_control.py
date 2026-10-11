"""Stage 9C D2 bounded three-hour soak: read-only status and single-round enqueue.

This is a deliberately operator-stepped scheduler, NOT the final autonomous
three-hour coordinator. It cannot start HTTP workers. All mutations require
--execute. Use the design document before adding unattended scheduling.
"""
from __future__ import annotations

import argparse
import json
import os
from sqlalchemy import text
from bf4ps.collection_jobs import enqueue_job
from scripts.stage9c_three_site_live_ignition import engine, validate
from scripts.stage9c_three_hour_soak_preflight import EXPECTED_BASELINE

RUN = "bf4ps-d2-three-hour-soak-20261011-v1"
ROUNDS = 12
ATTEMPT_CEILING = 108


def snapshot(conn):
    ids = sorted(validate(conn).values())
    jobs = conn.execute(text("""
        SELECT status, count(*) AS n FROM collection_jobs
        GROUP BY status ORDER BY status
    """)).all()
    events = conn.execute(text("""
        SELECT event_type, count(*) AS n FROM collection_events
        WHERE event_id > :base AND resource='detailed'
        GROUP BY event_type ORDER BY event_type
    """), {"base": EXPECTED_BASELINE}).all()
    attempts = conn.execute(text("""
        SELECT count(DISTINCT (job_id,attempt_number))
        FROM collection_events
        WHERE event_id > :base AND resource='detailed'
          AND event_type='collection_attempt_started'
    """), {"base": EXPECTED_BASELINE}).scalar_one()
    return {
        "soldier_ids": ids,
        "jobs": dict(jobs),
        "events": dict(events),
        "physical_attempts_started": int(attempts),
        "remaining_attempt_budget": ATTEMPT_CEILING - int(attempts),
    }


def status(e):
    with e.connect() as conn:
        result = snapshot(conn)
    print(json.dumps(result, sort_keys=True), flush=True)


def prepare_round(e, round_number):
    if os.uname().nodename != "tcou":
        raise RuntimeError("only tcou may enqueue")
    if not 1 <= round_number <= ROUNDS:
        raise RuntimeError("invalid round")
    with e.begin() as conn:
        # Serialize coordinator calls without taking locks on unrelated tables.
        conn.execute(text("SELECT pg_advisory_xact_lock(90841011, 3)"))
        state = snapshot(conn)
        if state["jobs"]:
            raise RuntimeError("previous round has unfinished jobs")
        if state["remaining_attempt_budget"] < len(state["soldier_ids"]):
            raise RuntimeError("insufficient remaining global attempt budget")
        # No second run of the same round, even if its jobs were already deleted.
        reason = f"{RUN}:round-{round_number:02d}"
        prior = conn.execute(text("""
            SELECT count(*) FROM collection_events
            WHERE event_id > :base AND resource='detailed'
              AND metadata->>'soak_reason'=:reason
        """), {"base": EXPECTED_BASELINE, "reason": reason}).scalar_one()
        if prior:
            raise RuntimeError("round already recorded")
        # Round 1 must begin from the verified baseline. Later rounds need a
        # durable manifest; do not allow them yet.
        if round_number != 1:
            raise RuntimeError("rounds 2-12 require durable manifest implementation")
        if state["physical_attempts_started"] != 0:
            raise RuntimeError("not at clean soak start")
        for sid in state["soldier_ids"]:
            enqueue_job(conn, soldier_id=sid, resource="detailed",
                        lane="background", priority_class="bootstrap",
                        reason=reason)
    print(f"ROUND PREPARED {round_number} jobs={len(state['soldier_ids'])}", flush=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=("status", "prepare-round"))
    p.add_argument("--round", type=int)
    p.add_argument("--execute", action="store_true")
    args = p.parse_args()
    e = engine()
    if args.command == "status":
        status(e)
    else:
        if not args.execute:
            p.error("prepare-round requires --execute")
        if args.round is None:
            p.error("--round is required")
        prepare_round(e, args.round)


if __name__ == "__main__":
    main()
