"""Crash-safe, no-secret coordinator intent journal for D2 synthetic cohorts.

The intent is persisted before any database transaction begins. It contains
only a manifest and its digest, never credentials or production identifiers.
On restart the coordinator can recover row IDs by the synthetic run prefix.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from sqlalchemy import text

from scripts.phase5b_three_site_manifest import validate_manifest_document


def write_intent(path: Path, document: dict) -> None:
    validate_manifest_document(document)
    if path.exists():
        raise RuntimeError("REFUSING to overwrite existing run intent")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(document, handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        directory = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except BaseException:
        # Leave any partial intent in place, preventing unsafe reuse.
        raise


def read_intent(path: Path) -> dict:
    document = json.loads(path.read_text(encoding="utf-8"))
    validate_manifest_document(document)
    return document


def recover_state(conn, manifest):
    """Recover only exact, marker-scoped rows after a coordinator crash.

    Fail closed on missing, partial or unexpected rows. Never delete anything.
    """
    from scripts.phase5b_three_site_d2_coordinator import cohort_prefix
    prefix = cohort_prefix(manifest.run_id)
    soldiers = conn.execute(text("""
        SELECT soldier_id FROM soldiers
        WHERE current_name LIKE :prefix ORDER BY soldier_id
    """), {"prefix": prefix + "%"}).scalars().all()
    if not soldiers:
        return None  # transaction never committed, safe to retry after checks
    if len(soldiers) != manifest.job_count:
        raise RuntimeError("REFUSING partial or mismatched synthetic soldier cohort")
    jobs = conn.execute(text("""
        SELECT job_id,soldier_id,reason FROM collection_jobs
        WHERE soldier_id=ANY(:ids) ORDER BY job_id
    """), {"ids": soldiers}).all()
    if len(jobs) != manifest.job_count or any(
        not row.reason.startswith(prefix) for row in jobs
    ) or {row.soldier_id for row in jobs} != set(soldiers):
        raise RuntimeError("REFUSING partial or mismatched synthetic jobs")
    collectors = conn.execute(text("""
        SELECT collector_uuid,collector_name FROM collectors
        WHERE collector_name LIKE :prefix
    """), {"prefix": prefix + "%"}).all()
    expected = set(manifest.payload()["collector_uuids"])
    if (len(collectors) != len(expected)
            or {str(row.collector_uuid) for row in collectors} != expected
            or any(row.collector_name != prefix + str(row.collector_uuid)
                   for row in collectors)):
        raise RuntimeError("REFUSING mismatched synthetic collectors")
    return {
        "run_id": manifest.run_id,
        "manifest_sha256": manifest.report()["sha256"],
        "soldier_ids": list(soldiers),
        "job_ids": [row.job_id for row in jobs],
        "worker_count": len(expected),
        "job_count": len(jobs),
    }


def write_state(path: Path, state: dict) -> None:
    """Durably publish a recovered or newly committed cohort state."""
    if path.exists():
        raise RuntimeError("REFUSING to overwrite existing state")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(state, handle, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    directory = os.open(str(path.parent), os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
