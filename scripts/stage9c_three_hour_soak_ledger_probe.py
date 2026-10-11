"""Transactional Stage 9C D2 soak ledger integration probe.

No schema migrations, HTTP, persistent run rows, or queued jobs.
Runs the real create/admit primitives inside PostgreSQL SAVEPOINTs and rolls
the outer transaction back. A prepared run with a future deadline is created
only inside the rollback-only transaction to exercise round admission.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import text

from scripts.stage9c_three_site_live_ignition import engine, validate
from scripts.stage9c_three_hour_soak_ledger import (
    RUN_ID, BASELINE_EVENT, create_prepared_run, admit_round, guard,
)


def main() -> None:
    e = engine()
    with e.connect() as conn:
        trans = conn.begin()
        try:
            guard(conn)
            ids = sorted(validate(conn).values())
            if conn.execute(text("SELECT count(*) FROM soak_runs")).scalar_one():
                raise RuntimeError("soak ledger already contains runs")
            if conn.execute(text("SELECT count(*) FROM collection_jobs")).scalar_one():
                raise RuntimeError("queue not empty")
            if conn.execute(text("SELECT max(event_id) FROM collection_events")).scalar_one() != BASELINE_EVENT:
                raise RuntimeError("unexpected event baseline")
            create_prepared_run(conn, ids)
            create_prepared_run(conn, ids)
            conn.execute(text("""
                UPDATE soak_runs
                SET state='running',
                    start_at=clock_timestamp() - interval '1 minute',
                    deadline_at=clock_timestamp() + interval '3 hours'
                WHERE run_id=:run
            """), {"run": RUN_ID})
            jobs = admit_round(conn, ids, 1)
            if len(jobs) != 9 or len(set(jobs)) != 9:
                raise RuntimeError("round did not admit nine unique jobs")
            if conn.execute(text("""
                SELECT count(*) FROM soak_round_jobs WHERE run_id=:run
            """), {"run": RUN_ID}).scalar_one() != 9:
                raise RuntimeError("job attribution missing")
            # Failed duplicate attempt must not poison the outer transaction:
            # Python guard rejects before any mutation.
            try:
                admit_round(conn, ids, 1)
            except RuntimeError as exc:
                if "already admitted" not in str(exc):
                    raise
            else:
                raise RuntimeError("duplicate round unexpectedly accepted")
            print(f"ROLLBACK PROBE PASS jobs={len(jobs)} duplicate_admission=rejected", flush=True)
        finally:
            trans.rollback()
    with e.connect() as conn:
        guard(conn)
        checks = {
            "runs": conn.execute(text("SELECT count(*) FROM soak_runs")).scalar_one(),
            "rounds": conn.execute(text("SELECT count(*) FROM soak_rounds")).scalar_one(),
            "attribution": conn.execute(text("SELECT count(*) FROM soak_round_jobs")).scalar_one(),
            "jobs": conn.execute(text("SELECT count(*) FROM collection_jobs")).scalar_one(),
        }
        if any(checks.values()):
            raise RuntimeError(f"rollback left persistent rows: {checks}")
        print(f"POST-ROLLBACK PASS {checks}", flush=True)


if __name__ == "__main__":
    main()
