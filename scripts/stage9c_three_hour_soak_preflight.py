"""Read-only preflight for the three-hour three-site D2 soak.

No jobs, HTTP, schema changes, or background processes are created.
Run on each of tcou, kah-01 and hnl-01 with D2 environment loaded.
"""
from __future__ import annotations

import argparse
import json
import os
from sqlalchemy import text

from scripts.stage9c_three_site_live_ignition import NODES, UUIDS, engine, validate

EXPECTED_BASELINE = 109
EXPECTED_EVENT_ROWS = 77
EXPECTED_SOLDIERS = 9
EXPECTED_SITES = 3


def inspect() -> dict:
    hostname = os.uname().nodename
    if hostname not in NODES:
        raise RuntimeError(f"refusing unexpected host {hostname}")
    e = engine()
    with e.connect() as conn:
        cohort = validate(conn)
        if len(cohort) != EXPECTED_SOLDIERS:
            raise RuntimeError("unexpected cohort size")
        baseline = conn.execute(
            text("SELECT COALESCE(MAX(event_id),0), count(*) FROM collection_events")
        ).one()
        queue = conn.execute(
            text("SELECT status, count(*) FROM collection_jobs GROUP BY status ORDER BY status")
        ).all()
        if queue:
            raise RuntimeError(f"outstanding queue: {queue}")
        if tuple(baseline) != (EXPECTED_BASELINE, EXPECTED_EVENT_ROWS):
            raise RuntimeError(f"event baseline changed: {tuple(baseline)}")
        counts = {
            table: conn.execute(text("SELECT count(*) FROM " + table)).scalar_one()
            for table in (
                "soldiers",
                "collectors",
                "collection_state",
                "detailed_stats_current",
                "detailed_stats_history",
            )
        }
        if counts["soldiers"] != EXPECTED_SOLDIERS or counts["collectors"] != EXPECTED_SITES:
            raise RuntimeError(f"unexpected inventory {counts}")
        missing = conn.execute(text("""
            SELECT s.soldier_id
            FROM soldiers s
            LEFT JOIN detailed_stats_current d USING (soldier_id)
            LEFT JOIN collection_state st USING (soldier_id)
            WHERE d.soldier_id IS NULL OR st.detailed_state IS DISTINCT FROM 'success'
            ORDER BY s.soldier_id
        """)).scalars().all()
        if missing:
            raise RuntimeError(f"cohort has incomplete baseline: {missing}")
        collectors = conn.execute(text("""
            SELECT hostname,collector_uuid,enabled,drained,retired_at
            FROM collectors ORDER BY hostname
        """)).mappings().all()
        if len(collectors) != EXPECTED_SITES or any(
            c["hostname"] not in NODES
            or c["collector_uuid"] != UUIDS[c["hostname"]]
            or not c["enabled"]
            or c["drained"]
            or c["retired_at"] is not None
            for c in collectors
        ):
            raise RuntimeError("collector registration mismatch")
        result = {
            "host": hostname,
            "db": "bf4ps_scratch_stage9c_d2",
            "baseline_event_id": int(baseline[0]),
            "event_rows": int(baseline[1]),
            "queue_jobs": 0,
            "soldier_ids": sorted(cohort.values()),
            "collectors": [c["hostname"] for c in collectors],
            "inventory": counts,
            "status": "PASS",
        }
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["preflight"])
    args = parser.parse_args()
    if args.command == "preflight":
        print(json.dumps(inspect(), sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
