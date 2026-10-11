"""Offline reconciliation of synthetic D2 claim-worker reports.

Checks manifest integrity, every planned worker identity, unique job ownership,
and exact agreement with committed database claim observations. No I/O.
"""
from __future__ import annotations

from collections import Counter

from scripts.phase5b_three_site_coordinator import FleetPlan
from scripts.phase5b_three_site_manifest import validate_manifest_document


def reconcile_claim_reports(document: dict, state: dict, reports: list[dict],
                            committed: dict) -> dict:
    manifest = validate_manifest_document(document)
    plan = FleetPlan.build(manifest.run_id, manifest.distribution)
    expected = {(w.host, w.worker_index): w for w in plan.workers()}
    if not isinstance(reports, list) or len(reports) != len(expected):
        raise ValueError("missing or excess worker reports")
    if (state.get("run_id") != manifest.run_id
            or state.get("manifest_sha256") != document["sha256"]):
        raise ValueError("coordinator state mismatch")
    job_ids = state.get("job_ids")
    if (not isinstance(job_ids, list) or len(job_ids) != manifest.job_count
            or len(set(job_ids)) != manifest.job_count):
        raise ValueError("invalid expected job cohort")
    if committed.get("run_id") != manifest.run_id or committed.get("jobs") != len(job_ids):
        raise ValueError("database observation mismatch")
    seen_workers = set()
    seen_jobs = set()
    reported_claims = {}
    by_host = Counter()
    for report in reports:
        if not isinstance(report, dict):
            raise ValueError("invalid worker report")
        key = (report.get("host"), report.get("worker_index"))
        if key not in expected or key in seen_workers:
            raise ValueError("unknown or duplicate worker report")
        worker = expected[key]
        if (report.get("run_id") != manifest.run_id
                or report.get("workers_on_host") != worker.workers_on_host
                or report.get("collector_uuid") != str(worker.collector_uuid)
                or report.get("manifest_sha256") != document["sha256"]
                or report.get("mode") != "synthetic-d2-claims"
                or report.get("http_requests") != 0):
            raise ValueError("worker report identity or safety mismatch")
        claims = report.get("claims")
        if (not isinstance(claims, list)
                or len(claims) > manifest.claim_limit_per_worker
                or report.get("database_writes") != len(claims)):
            raise ValueError("worker claim count mismatch")
        seen_workers.add(key)
        for claim in claims:
            if (claim.get("host") != worker.host
                    or claim.get("worker_index") != worker.worker_index
                    or claim.get("collector_uuid") != str(worker.collector_uuid)
                    or claim.get("job_id") not in job_ids
                    or not isinstance(claim.get("attempt_count"), int)
                    or claim["attempt_count"] != 1
                    or not isinstance(claim.get("lease_token"), str)
                    or not claim["lease_token"]):
                raise ValueError("invalid synthetic claim")
            jid = claim["job_id"]
            if jid in seen_jobs:
                raise ValueError("duplicate claimed job")
            seen_jobs.add(jid)
            reported_claims[jid] = str(worker.collector_uuid)
            by_host[worker.host] += 1
    db_claims = committed.get("claims")
    if not isinstance(db_claims, list) or committed.get("claimed") != len(db_claims):
        raise ValueError("invalid database claim count")
    db_owners = {}
    for claim in db_claims:
        jid = claim.get("job_id")
        if (jid not in job_ids or jid in db_owners
                or claim.get("attempt_count") != 1):
            raise ValueError("invalid committed job")
        db_owners[jid] = claim.get("collector_uuid")
    if db_owners != reported_claims:
        raise ValueError("worker reports disagree with committed PostgreSQL claims")
    return {
        "status": "pass", "run_id": manifest.run_id,
        "workers": len(seen_workers), "jobs": len(job_ids),
        "claimed": len(seen_jobs), "unclaimed": len(job_ids) - len(seen_jobs),
        "duplicate_committed_jobs": 0,
        "per_host": dict(sorted(by_host.items())),
        "http_requests": 0,
    }
