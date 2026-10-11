"""Rollback-only D2 lifecycle integration test: ignition, stop, deadline.

No HTTP and no persisted run; verifies fail-closed transitions in the
actual isolated PostgreSQL database.
"""
from sqlalchemy import text
from scripts.stage9c_three_site_live_ignition import engine
from scripts.stage9c_three_hour_soak_cohort import cohort_ids
from scripts.stage9c_three_hour_soak_ledger import RUN_ID, create_prepared_run
from scripts.stage9c_three_hour_soak_lifecycle import ignite, stop, http_allowed


def main():
    e = engine()
    with e.connect() as conn:
        tx = conn.begin()
        try:
            ids = cohort_ids(conn)
            if conn.execute(text("SELECT count(*) FROM soak_runs")).scalar_one():
                raise RuntimeError("existing soak run")
            if conn.execute(text("SELECT count(*) FROM collection_jobs")).scalar_one():
                raise RuntimeError("queue not empty")
            create_prepared_run(conn, ids)
            if http_allowed(conn, site="tcou"):
                raise RuntimeError("prepared run incorrectly allows HTTP")
            started = ignite(conn, ids)
            if not started["start_at"] < started["deadline_at"]:
                raise RuntimeError("deadline invalid")
            if not http_allowed(conn, site="tcou"):
                raise RuntimeError("running run incorrectly blocks HTTP")
            try:
                ignite(conn, ids)
            except RuntimeError as exc:
                if "ignition refused" not in str(exc):
                    raise
            else:
                raise RuntimeError("duplicate ignition accepted")
            if stop(conn, "rollback integration test") != "stopping":
                raise RuntimeError("stop transition failed")
            if http_allowed(conn, site="tcou"):
                raise RuntimeError("stopping run still allows HTTP")
            print("LIFECYCLE PASS prepared=blocked ignition=allowed duplicate=rejected stop=blocked")
        finally:
            tx.rollback()
    with e.connect() as conn:
        count = conn.execute(text("SELECT count(*) FROM soak_runs")).scalar_one()
        if count:
            raise RuntimeError(f"rollback left {count} runs")
        print("LIFECYCLE ROLLBACK PASS runs=0")


if __name__ == "__main__":
    main()
