"""Guarded worker-side D2 claim executor. Never makes HTTP requests.

Requires an explicit manifest, an explicit synthetic soldier cohort, and
--execute. No collector registration or schema mutations occur here.
Coordinator must provision synthetic collectors/jobs separately.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import time

from sqlalchemy import create_engine, text

from bf4ps.collection_jobs import claim_next_job
from scripts.phase5b_three_site_manifest import validate_manifest_document
from scripts.phase5b_three_site_worker import WorkerConfig, check_database_identity


def validate_claim_cohort(conn, *, run_id: str, soldier_ids: list[int],
                          collector_uuid, host: str) -> None:
    if not soldier_ids or len(soldier_ids) != len(set(soldier_ids)):
        raise ValueError("nonempty unique synthetic soldier cohort required")
    if len(soldier_ids) > 10000 or any(i <= 0 for i in soldier_ids):
        raise ValueError("invalid synthetic cohort")
    prefix = f"synthetic-three-site-{run_id}-"
    rows = conn.execute(text("""
        SELECT soldier_id,current_name FROM soldiers
        WHERE soldier_id=ANY(:ids)
    """), {"ids": soldier_ids}).all()
    if len(rows) != len(soldier_ids) or any(not r.current_name.startswith(prefix) for r in rows):
        raise RuntimeError("REFUSING nonmatching synthetic soldier cohort")
    row = conn.execute(text("""
        SELECT hostname,lane FROM collectors WHERE collector_uuid=:uuid
    """), {"uuid": collector_uuid}).one_or_none()
    if row is None or row.hostname != host or row.lane != "background":
        raise RuntimeError("REFUSING missing or mismatched synthetic collector")
    jobs = conn.execute(text("""
        SELECT soldier_id,resource,lane FROM collection_jobs
        WHERE soldier_id=ANY(:ids)
    """), {"ids": soldier_ids}).all()
    if len(jobs) != len(soldier_ids) or any(
        j.resource != "detailed" or j.lane != "background" for j in jobs
    ):
        raise RuntimeError("REFUSING missing or unexpected synthetic jobs")


def run(*, manifest_document: dict, host: str, index: int,
        soldier_ids: list[int], execute: bool, url: str | None):
    manifest = validate_manifest_document(manifest_document)
    count = manifest.distribution.get(host, 0)
    if count < 1:
        raise ValueError("host not enabled in manifest")
    worker = WorkerConfig.build(host=host, worker_index=index,
                                workers_on_host=count, run_id=manifest.run_id)
    report = worker.report()
    report["manifest_sha256"] = manifest.report()["sha256"]
    if not execute:
        return report
    if not url:
        raise ValueError("BF4PS_STAGE9C_D2_URL required")
    check_database_identity(url)
    engine = create_engine(url, connect_args={"connect_timeout": 5},
                           pool_size=1, max_overflow=0)
    claims = []
    try:
        with engine.connect() as conn:
            validate_claim_cohort(conn, run_id=manifest.run_id,
                                  soldier_ids=soldier_ids,
                                  collector_uuid=worker.collector_uuid, host=host)
            conn.rollback()
        for _ in range(manifest.claim_limit_per_worker):
            started = time.monotonic()
            with engine.begin() as conn:
                job = claim_next_job(
                    conn, collector_uuid=worker.collector_uuid,
                    resource="detailed", lane="background",
                    allowed_soldier_ids=soldier_ids,
                    lease_seconds=manifest.lease_seconds)
            if job is None:
                break
            claims.append({
                "host": host, "worker_index": index,
                "collector_uuid": str(worker.collector_uuid),
                "job_id": job.job_id, "soldier_id": job.soldier_id,
                "attempt_count": job.attempt_count,
                "lease_token": str(job.lease_token),
                "claim_elapsed_ms": round((time.monotonic()-started)*1000, 3),
            })
    finally:
        engine.dispose()
    report.update(mode="synthetic-d2-claims", database_writes=len(claims),
                  claims=claims)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--worker-index", required=True, type=int)
    parser.add_argument("--soldier-id", type=int, action="append", default=[])
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    try:
        with open(args.manifest, encoding="utf-8") as handle:
            document = json.load(handle)
        host = socket.gethostname().split(".")[0].lower()
        report = run(
            manifest_document=document, host=host, index=args.worker_index,
            soldier_ids=args.soldier_id, execute=args.execute,
            url=os.environ.get("BF4PS_STAGE9C_D2_URL"))
        print(json.dumps(report, sort_keys=True))
    except (OSError, ValueError, RuntimeError, TypeError, KeyError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
