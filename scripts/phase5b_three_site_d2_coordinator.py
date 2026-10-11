"""D2-only synthetic cohort coordinator for future three-site claim tests.

prepare/verify/cleanup require --execute and exact D2 credentials.
No HTTP, production access, schema migrations or remote process launches.
The coordinator refuses nonempty D2 tables before preparing a new cohort.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, text

from bf4ps.collection_jobs import enqueue_job
from scripts.phase5b_three_site_manifest import validate_manifest_document
from scripts.phase5b_three_site_worker import check_database_identity
from scripts.phase5b_three_site_recovery import write_intent, read_intent, recover_state


def cohort_prefix(run_id: str) -> str:
    return f"synthetic-three-site-{run_id}-"


def assert_clean(conn):
    tables = ("soldiers", "collection_jobs", "collection_events",
              "collection_state", "collectors")
    counts = {t: conn.execute(text(f"SELECT count(*) FROM {t}")).scalar_one()
              for t in tables}
    if any(counts.values()):
        raise RuntimeError("REFUSING nonempty D2 core tables")
    return counts


def prepare(conn, manifest):
    assert_clean(conn)
    prefix = cohort_prefix(manifest.run_id)
    plan = manifest.payload()
    for worker in plan["collector_uuids"]:
        # Host is recovered from the immutable manifest's worker configuration.
        from scripts.phase5b_three_site_coordinator import FleetPlan
        identities = {str(w.collector_uuid): w for w in FleetPlan.build(
            manifest.run_id, manifest.distribution).workers()}
        identity = identities[worker]
        conn.execute(text("""
            INSERT INTO collectors (collector_uuid,collector_name,hostname,lane,egress_key)
            VALUES (:uuid,:name,:host,'background',:egress)
        """), {"uuid": worker, "name": prefix + worker,
               "host": identity.host, "egress": "synthetic-" + identity.host})
    soldiers = []
    jobs = []
    for i in range(manifest.job_count):
        sid = conn.execute(text("""
            INSERT INTO soldiers (persona_id,platform,current_name,first_seen_at,last_seen_at)
            VALUES (:persona,'pc',:name,clock_timestamp(),clock_timestamp())
            RETURNING soldier_id
        """), {"persona": 1_600_000_000 + uuid4().int % 100_000_000,
               "name": prefix + str(i)}).scalar_one()
        soldiers.append(sid)
        jid = enqueue_job(conn, soldier_id=sid, resource="detailed",
                          lane="background", priority_class="bootstrap",
                          reason=prefix + str(i))
        jobs.append(jid)
    return {"run_id": manifest.run_id, "manifest_sha256": manifest.report()["sha256"],
            "soldier_ids": soldiers, "job_ids": jobs,
            "worker_count": plan["worker_count"], "job_count": len(jobs)}


def verify(conn, manifest, state):
    validate_state(manifest, state)
    rows = conn.execute(text("""
        SELECT j.job_id,j.soldier_id,j.status,j.attempt_count,
               j.collector_uuid,j.lease_token,s.current_name
        FROM collection_jobs j JOIN soldiers s ON s.soldier_id=j.soldier_id
        WHERE j.job_id=ANY(:ids)
    """), {"ids": state["job_ids"]}).mappings().all()
    if len(rows) != manifest.job_count:
        raise RuntimeError("synthetic jobs missing")
    expected = set(state["soldier_ids"])
    prefix = cohort_prefix(manifest.run_id)
    allowed_workers = set(manifest.payload()["collector_uuids"])
    claims = []
    for row in rows:
        if row["soldier_id"] not in expected or not row["current_name"].startswith(prefix):
            raise RuntimeError("REFUSING mismatched synthetic job")
        if row["status"] in ("claimed", "running"):
            if str(row["collector_uuid"]) not in allowed_workers or row["lease_token"] is None:
                raise RuntimeError("invalid claim ownership")
            claims.append({"job_id": row["job_id"], "attempt_count": row["attempt_count"],
                           "collector_uuid": str(row["collector_uuid"])})
    return {"run_id": manifest.run_id, "jobs": len(rows),
            "claimed": len(claims), "unclaimed": len(rows)-len(claims),
            "claims": sorted(claims, key=lambda item: item["job_id"])}


def validate_state(manifest, state):
    if (state.get("run_id") != manifest.run_id
            or state.get("manifest_sha256") != manifest.report()["sha256"]
            or len(state.get("soldier_ids", [])) != manifest.job_count
            or len(state.get("job_ids", [])) != manifest.job_count
            or len(set(state["soldier_ids"])) != manifest.job_count
            or len(set(state["job_ids"])) != manifest.job_count
            or any(not isinstance(i, int) or i <= 0
                   for i in state["soldier_ids"] + state["job_ids"])):
        raise ValueError("invalid or mismatched coordinator state")


def cleanup(conn, manifest, state):
    verify(conn, manifest, state)
    prefix = cohort_prefix(manifest.run_id)
    active = conn.execute(text("""
        SELECT count(*) FROM collection_jobs
        WHERE job_id=ANY(:ids) AND status IN ('claimed','running')
    """), {"ids": state["job_ids"]}).scalar_one()
    if active:
        raise RuntimeError("REFUSING cleanup while synthetic jobs are claimed or running")
    conn.execute(text("DELETE FROM collection_events WHERE soldier_id=ANY(:ids)"),
                 {"ids": state["soldier_ids"]})
    conn.execute(text("DELETE FROM collection_state WHERE soldier_id=ANY(:ids)"),
                 {"ids": state["soldier_ids"]})
    conn.execute(text("DELETE FROM collection_jobs WHERE job_id=ANY(:ids)"),
                 {"ids": state["job_ids"]})
    conn.execute(text("DELETE FROM soldiers WHERE soldier_id=ANY(:ids) AND left(current_name, length(:prefix)) = :prefix"),
                 {"ids": state["soldier_ids"], "prefix": prefix})
    conn.execute(text("DELETE FROM collectors WHERE collector_uuid=ANY(:ids) AND left(collector_name, length(:prefix)) = :prefix"),
                 {"ids": manifest.payload()["collector_uuids"], "prefix": prefix})
    return assert_clean(conn)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "recover", "verify", "cleanup"))
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    if not args.execute:
        parser.error("--execute required for D2 operations")
    url = os.environ.get("BF4PS_STAGE9C_D2_URL")
    if not url:
        parser.error("BF4PS_STAGE9C_D2_URL required")
    try:
        manifest = validate_manifest_document(json.loads(args.manifest.read_text()))
        intent_path = args.state.with_suffix(args.state.suffix + ".intent")
        if args.action == "prepare":
            if args.state.exists():
                raise RuntimeError("REFUSING existing state")
            write_intent(intent_path, manifest.report())
            state = None
        else:
            if read_intent(intent_path) != manifest.report():
                raise RuntimeError("REFUSING mismatched intent")
            state = None if args.action == "recover" else json.loads(args.state.read_text())
        check_database_identity(url)
        engine = create_engine(url, connect_args={"connect_timeout": 5})
        try:
            with engine.begin() as conn:
                if args.action == "prepare":
                    result = prepare(conn, manifest)
                elif args.action == "recover":
                    result = recover_state(conn, manifest)
                    if result is None:
                        raise RuntimeError("No committed synthetic cohort to recover")
                elif args.action == "verify":
                    result = verify(conn, manifest, state)
                else:
                    result = cleanup(conn, manifest, state)
        finally:
            engine.dispose()
        if args.action in ("prepare", "recover"):
            if args.state.exists():
                raise RuntimeError("REFUSING existing state file")
            from scripts.phase5b_three_site_recovery import write_state
            write_state(args.state, result)
        print(json.dumps(result, sort_keys=True))
    except (OSError, ValueError, RuntimeError, TypeError, KeyError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
