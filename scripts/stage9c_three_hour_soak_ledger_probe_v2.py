"""Rollback-only D2 integration test for atomic soak admission."""
from sqlalchemy import text
from scripts.stage9c_three_site_live_ignition import engine
from scripts.stage9c_three_hour_soak_cohort import cohort_ids
from scripts.stage9c_three_hour_soak_ledger import (
    RUN_ID, BASELINE_EVENT, create_prepared_run, admit_round, guard,
)


def main():
    e = engine()
    with e.connect() as conn:
        tx = conn.begin()
        try:
            ids = cohort_ids(conn)
            if conn.execute(text("SELECT count(*) FROM soak_runs")).scalar_one():
                raise RuntimeError("run ledger is not empty")
            if conn.execute(text("SELECT count(*) FROM collection_jobs")).scalar_one():
                raise RuntimeError("queue is not empty")
            if conn.execute(text("SELECT coalesce(max(event_id),0) FROM collection_events")).scalar_one() != BASELINE_EVENT:
                raise RuntimeError("event baseline changed")
            create_prepared_run(conn, ids)
            create_prepared_run(conn, ids)
            conn.execute(text("""
                UPDATE soak_runs SET state='running',
                start_at=clock_timestamp()-interval '1 minute',
                deadline_at=clock_timestamp()+interval '3 hours'
                WHERE run_id=:run
            """), {"run": RUN_ID})
            jobs = admit_round(conn, ids, 1)
            if len(jobs) != 9 or len(set(jobs)) != 9:
                raise RuntimeError("nine unique jobs not admitted")
            if conn.execute(text("SELECT count(*) FROM soak_round_jobs")).scalar_one() != 9:
                raise RuntimeError("missing job attribution")
            try:
                admit_round(conn, ids, 1)
            except RuntimeError as exc:
                if "already admitted" not in str(exc):
                    raise
            else:
                raise RuntimeError("duplicate round accepted")
            print("TRANSACTION PROBE PASS: nine attributed jobs, duplicate rejected")
        finally:
            tx.rollback()
    with e.connect() as conn:
        guard(conn)
        counts = {table: conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
                  for table in ("soak_runs", "soak_rounds", "soak_round_jobs", "collection_jobs")}
        if any(counts.values()):
            raise RuntimeError(f"rollback residue: {counts}")
        print(f"ROLLBACK PASS {counts}")


if __name__ == "__main__":
    main()
