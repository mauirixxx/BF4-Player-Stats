"""Fail-closed D4 first-30 queue preparation and read-only verification.

No HTTP in this module. Workload execution requires a separate reviewed runner.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from uuid import NAMESPACE_DNS, uuid5

from sqlalchemy import create_engine, text
from bf4ps.collection_jobs import enqueue_job

DB = "bf4ps_scratch_stage9c_d4"
ROLE = "bf4ps_stage9c_d2"
REV = "0006_stage9c_soak_round_ledger"
SHA = "7bd0ed22ba19f2f7e8d4b6acf9c0c113115a50a9e8f5bc74a6caab5b64e215d2"
RUN = "bf4ps-d4-real30-20261011-v1"
NODES = ("tcou", "kah-01", "hnl-01")
RESOURCES = ("detailed", "weapons", "vehicles")
MANIFEST = Path(__file__).resolve().parents[1] / "docs/stage9c-d3-real-300-candidate-manifest-2026-10-11.json"


def cohort():
    raw = MANIFEST.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SHA:
        raise RuntimeError("frozen manifest mismatch")
    rows = json.loads(raw)["rows"]
    if len(rows) != 300:
        raise RuntimeError("manifest must contain 300")
    # Explicit per-site platform quotas: 10 each platform globally.
    quotas = {
        "tcou": {"pc": 4, "ps4": 3, "xboxone": 3},
        "kah-01": {"pc": 3, "ps4": 4, "xboxone": 3},
        "hnl-01": {"pc": 3, "ps4": 3, "xboxone": 4},
    }
    selected = [r for node in NODES for platform in ("pc", "ps4", "xboxone")
                for r in [x for x in rows if x["site"] == node and x["platform"] == platform][:quotas[node][platform]]]
    if len(selected) != 30 or any(sum(r["site"] == n for r in selected) != 10 for n in NODES):
        raise RuntimeError("30-player site split failed")
    if any(sum(r["platform"] == p for r in selected) != 10 for p in ("pc","ps4","xboxone")):
        raise RuntimeError("30-player platform split failed")
    return selected


def engine():
    source = os.environ["BF4PS_STAGE9C_D2_URL"]
    if not source.startswith("postgresql+psycopg://"):
        raise RuntimeError("expected existing psycopg SQLAlchemy URL")
    from sqlalchemy.engine import make_url
    url = make_url(source)
    if url.database != "bf4ps_scratch_stage9c_d2" or url.username != ROLE:
        raise RuntimeError("unexpected D2 credential source")
    return create_engine(url.set(database=DB), pool_pre_ping=True)


def guard(conn, *, pristine=False):
    row = conn.execute(text("SELECT current_database(),current_user,pg_is_in_recovery(),current_setting('transaction_read_only')")).one()
    revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    if tuple(row) != (DB, ROLE, False, "off") or revision != REV:
        raise RuntimeError("D4 database/role/revision/primary guard failed")
    rows = conn.execute(text("SELECT persona_id,platform,current_name,soldier_id FROM soldiers")).mappings().all()
    expected = {(r["persona_id"], r["platform"], r["name"]) for r in json.loads(MANIFEST.read_text())["rows"]}
    if len(rows) != 300 or {(r["persona_id"], r["platform"], r["current_name"]) for r in rows} != expected:
        raise RuntimeError("D4 soldier cohort does not match manifest")
    states = conn.execute(text("SELECT count(*) FROM collection_state")).scalar_one()
    if states != 300:
        raise RuntimeError("D4 state count mismatch")
    if pristine:
        for table in ("collection_jobs", "collection_events", "collectors", "soak_runs"):
            if conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() != 0:
                raise RuntimeError(f"D4 is not pristine: {table}")
    return {(r["persona_id"], r["platform"]): r["soldier_id"] for r in rows}


def prepare(e):
    if os.uname().nodename != "tcou":
        raise RuntimeError("prepare only from tcou")
    with e.begin() as conn:
        ids = guard(conn, pristine=True)
        selected = cohort()
        for node in NODES:
            identity = uuid5(NAMESPACE_DNS, RUN + ":" + node)
            conn.execute(text("""
                INSERT INTO collectors(collector_uuid,collector_name,hostname,lane,egress_key,enabled,drained)
                VALUES(:id,:name,:host,'background',:egress,true,false)
            """), {"id": identity, "name": RUN + ":" + node, "host": node, "egress": RUN + ":" + node})
        for row in selected:
            sid = ids[(row["persona_id"], row["platform"])]
            for resource in RESOURCES:
                enqueue_job(conn, soldier_id=sid, resource=resource,
                            lane="background", priority_class="bootstrap", reason=RUN)
    print("D4 PREPARE PASS: 30 real soldiers, 90 pending jobs, three registered collectors, zero HTTP", flush=True)



def repair_unstarted(e):
    """Replace mistakenly PC-only queue; only allowed before any HTTP/claim."""
    if os.uname().nodename != "tcou":
        raise RuntimeError("repair only from tcou")
    with e.begin() as conn:
        ids = guard(conn)
        if conn.execute(text("SELECT count(*) FROM collection_events")).scalar_one():
            raise RuntimeError("cannot repair after any collection events")
        rows = conn.execute(text("SELECT status,attempt_count,reason FROM collection_jobs FOR UPDATE")).all()
        if len(rows) != 90 or any(status != "pending" or attempts != 0 or reason != RUN
                                  for status, attempts, reason in rows):
            raise RuntimeError("cannot repair modified queue")
        conn.execute(text("DELETE FROM collection_jobs"))
        for row in cohort():
            sid = ids[(row["persona_id"], row["platform"])]
            for resource in RESOURCES:
                enqueue_job(conn,soldier_id=sid,resource=resource,lane="background",
                            priority_class="bootstrap",reason=RUN)
    print("D4 REPAIR PASS: 10 PC, 10 PS4, 10 Xbox One; 90 pending, zero HTTP",flush=True)

def verify(e):
    with e.connect() as conn:
        ids = guard(conn)
        selected = cohort()
        chosen = {ids[(r["persona_id"], r["platform"])] for r in selected}
        jobs = conn.execute(text("SELECT soldier_id,resource,status FROM collection_jobs")).all()
        collectors = conn.execute(text("SELECT collector_uuid,hostname,egress_key,enabled,drained FROM collectors")).all()
        events = conn.execute(text("SELECT count(*) FROM collection_events")).scalar_one()
        if len(jobs) != 90 or {(sid, resource) for sid, resource, _ in jobs} != {(sid, resource) for sid in chosen for resource in RESOURCES}:
            raise RuntimeError("D4 job cohort mismatch")
        if len(collectors) != 3 or any(uuid != uuid5(NAMESPACE_DNS, RUN + ":" + node) or egress != RUN + ":" + node or not enabled or drained for uuid, node, egress, enabled, drained in collectors):
            raise RuntimeError("D4 collector identity mismatch")
        print(json.dumps({"database": DB, "soldiers": 300, "first_batch": 30, "jobs": len(jobs), "job_statuses": {s: sum(j.status == s for j in jobs) for s in sorted({j.status for j in jobs})}, "events": events, "collectors": len(collectors), "http_authorized": False}, sort_keys=True))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=("prepare", "verify", "repair-unstarted"))
    p.add_argument("--execute", action="store_true")
    a = p.parse_args()
    e = engine()
    if a.command == "prepare":
        if not a.execute:
            p.error("prepare requires --execute")
        prepare(e)
    else:
        verify(e)


if __name__ == "__main__":
    main()
