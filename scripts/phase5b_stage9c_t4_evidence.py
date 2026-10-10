#!/usr/bin/env python3
"""Read-only T4 rollback evidence: capture and compare full ordered row fingerprints.

Capture uses a single REPEATABLE READ READ ONLY transaction. No HTTP or writes.
The snapshot file is local; comparison never connects to PostgreSQL.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
from uuid import UUID
from sqlalchemy import create_engine, text
from scripts.phase5b_stage9c_postgres_integration import (
    EXPECTED_DATABASE, EXPECTED_IP, EXPECTED_USER, refuse_unsafe_target,
)

TABLES = ("collectors", "soldiers", "collection_jobs", "collection_events",
          "stage9c_supervision_runs")
# All tables are expected to contain only disposable T4 fixture data.
def snapshot(conn, marker):
    ident = conn.execute(text("""
        SELECT current_database(), current_user, inet_server_addr(),
               pg_is_in_recovery(), current_setting('transaction_read_only'),
               current_setting('transaction_isolation')
    """)).one()
    actual = (ident[0], ident[1], str(ident[2]), ident[3], ident[4], ident[5])
    expected = (EXPECTED_DATABASE, EXPECTED_USER, EXPECTED_IP, False, "on", "repeatable read")
    if actual != expected:
        raise RuntimeError(f"REFUSING unexpected scratch identity/isolation: {actual}")
    rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    if rev != "0004_stage9c_supervision_runs":
        raise RuntimeError("REFUSING Alembic revision drift")
    result = {"format": 1, "marker": marker, "database": EXPECTED_DATABASE,
              "revision": rev, "tables": {}}
    for table in TABLES:
        # Hash every row, not only marker-matching rows; rejects contamination.
        rows = conn.execute(text(f"""
            SELECT to_jsonb(t)::text AS payload FROM public.{table} AS t
            ORDER BY to_jsonb(t)::text
        """)).scalars()
        count = 0
        digest = hashlib.sha256()
        for row in rows:
            digest.update(row.encode("utf-8"))
            digest.update(b"\\n")
            count += 1
        result["tables"][table] = {"rows": count, "sha256": digest.hexdigest()}
    events = conn.execute(text("""
        SELECT event_type, COUNT(*) FROM collection_events
        WHERE metadata->>'stage9c_t4_marker'=:marker
        GROUP BY event_type ORDER BY event_type
    """), {"marker": marker}).all()
    result["marked_event_counts"] = {kind: count for kind, count in events}
    return result

def compare(before, after):
    if before != after:
        differences = [key for key in ("format","marker","database","revision","tables",
                                         "marked_event_counts") if before.get(key)!=after.get(key)]
        raise RuntimeError("REFUSING evidence mismatch: " + ", ".join(differences))
    return True

def main():
    p = argparse.ArgumentParser(description=__doc__)
    modes = p.add_mutually_exclusive_group(required=True)
    modes.add_argument("--capture", action="store_true")
    modes.add_argument("--compare", action="store_true")
    p.add_argument("--run-id", help="T4 fixture UUID (capture)")
    p.add_argument("--output", help="New local JSON file (capture)")
    p.add_argument("--before", help="Existing before JSON (compare)")
    p.add_argument("--after", help="Existing after JSON (compare)")
    args = p.parse_args()
    if args.compare:
        if not args.before or not args.after or args.run_id or args.output:
            p.error("compare requires --before and --after only")
        before = json.loads(Path(args.before).read_text())
        after = json.loads(Path(args.after).read_text())
        compare(before, after)
        print("PASS: exact read-only T4 evidence match")
        return
    if not args.run_id or not args.output or args.before or args.after:
        p.error("capture requires --run-id and --output only")
    marker = "stage9c_t4_" + str(UUID(args.run_id))
    url = os.environ.get("BF4PS_STAGE9C_INTEGRATION_URL", "")
    refuse_unsafe_target(url)
    path = Path(args.output)
    if path.exists():
        raise RuntimeError("REFUSING overwrite of existing evidence file")
    engine = create_engine(url, pool_pre_ping=True, connect_args={
        "connect_timeout": 5, "options": "-c statement_timeout=15000",
    })
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            try:
                data = snapshot(conn, marker)
            finally:
                conn.rollback()
        with path.open("x", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\\n")
        print("PASS: read-only evidence captured", path)
        print("TABLE COUNTS", {k:v["rows"] for k,v in data["tables"].items()})
        print("MARKED EVENT COUNTS", data["marked_event_counts"])
    finally:
        engine.dispose()

if __name__ == "__main__":
    main()
