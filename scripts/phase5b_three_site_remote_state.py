"""Reconstruct the coordinator's D2 synthetic state read-only on a remote host.

Only use for already-prepared, digest-verified scratch D2 cohorts. No HTTP.
The coordinator's original durable state remains authoritative for cleanup.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from sqlalchemy import create_engine, text

from scripts.phase5b_three_site_d2_coordinator import cohort_prefix, validate_state
from scripts.phase5b_three_site_manifest import validate_manifest_document
from scripts.phase5b_three_site_worker import check_database_identity


def reconstruct(conn, manifest):
    rows = conn.execute(text("""
        SELECT s.soldier_id,j.job_id
        FROM soldiers s
        JOIN collection_jobs j ON j.soldier_id=s.soldier_id
        WHERE left(s.current_name, length(:prefix)) = :prefix
        ORDER BY s.soldier_id
    """), {"prefix": cohort_prefix(manifest.run_id)}).all()
    if len(rows) != manifest.job_count:
        raise RuntimeError("REFUSING incomplete synthetic cohort")
    state = {
        "run_id": manifest.run_id,
        "manifest_sha256": manifest.report()["sha256"],
        "soldier_ids": [r.soldier_id for r in rows],
        "job_ids": [r.job_id for r in rows],
        "job_count": manifest.job_count,
        "worker_count": manifest.payload()["worker_count"],
    }
    validate_state(manifest, state)
    return state


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("REFUSING existing state")
    manifest = validate_manifest_document(json.loads(args.manifest.read_text()))
    url = os.environ.get("BF4PS_STAGE9C_D2_URL")
    if not url:
        parser.error("D2 credentials required")
    check_database_identity(url)
    engine = create_engine(url, connect_args={"connect_timeout": 5})
    try:
        with engine.connect() as conn:
            state = reconstruct(conn, manifest)
    finally:
        engine.dispose()
    fd = os.open(args.output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(state, stream, sort_keys=True)
        stream.write("\n")
    print(json.dumps({"run_id": manifest.run_id, "job_count": len(state["job_ids"]),
                      "manifest_sha256": state["manifest_sha256"]}))


if __name__ == "__main__":
    main()
