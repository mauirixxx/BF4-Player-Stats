"""Validate actual three-host dry-run worker reports without database access.

Input is a JSON array of reports from separately executed host-local workers.
The coordinator checks planned identity, host, index, and report uniqueness.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.phase5b_three_site_coordinator import FleetPlan


def validate_worker_reports(plan: FleetPlan, reports: list[dict]) -> dict:
    expected = {(w.host, w.worker_index): w for w in plan.workers()}
    if len(reports) != len(expected):
        raise ValueError(f"expected {len(expected)} reports, received {len(reports)}")
    seen = set()
    uuids = set()
    for report in reports:
        if not isinstance(report, dict):
            raise ValueError("report must be an object")
        key = (report.get("host"), report.get("worker_index"))
        if key not in expected or key in seen:
            raise ValueError("unknown or repeated host/worker report")
        worker = expected[key]
        if (report.get("run_id") != plan.run_id
                or report.get("workers_on_host") != worker.workers_on_host
                or report.get("collector_uuid") != str(worker.collector_uuid)
                or report.get("mode") != "dry-run"
                or report.get("database_writes") != 0
                or report.get("http_requests") != 0):
            raise ValueError("report disagrees with plan or violates dry-run contract")
        seen.add(key)
        uuids.add(report["collector_uuid"])
    if len(uuids) != len(expected):
        raise ValueError("duplicate collector identities")
    return {"status": "pass", "run_id": plan.run_id, "worker_count": len(seen),
            "unique_collectors": len(uuids),
            "hosts": sorted({host for host, _ in seen}),
            "database_writes": 0, "http_requests": 0}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--tcou", type=int, default=3)
    parser.add_argument("--kah-01", type=int, default=3)
    parser.add_argument("--hnl-01", type=int, default=2)
    parser.add_argument("--reports", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        plan = FleetPlan.build(args.run_id, {
            "tcou": args.tcou, "kah-01": args.kah_01, "hnl-01": args.hnl_01
        })
        reports = json.loads(args.reports.read_text())
        print(json.dumps(validate_worker_reports(plan, reports), sort_keys=True))
    except (ValueError, OSError, TypeError, KeyError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
