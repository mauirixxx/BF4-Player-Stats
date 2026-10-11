"""Rollback-only real-DB D2 physical-start gate tests; no HTTP.

Checks deadline, stop, attribution, identity and budget boundaries by
temporarily changing constants in the imported gate module (not DB caps).
All changes are within a single rolled-back PostgreSQL transaction.
"""
from types import SimpleNamespace
from sqlalchemy import text
from scripts.stage9c_three_site_live_ignition import engine, RUN, UUIDS
from scripts.stage9c_three_hour_soak_cohort import cohort_ids
from scripts.stage9c_three_hour_soak_ledger import RUN_ID, create_prepared_run, admit_round
from scripts.stage9c_three_hour_soak_lifecycle import ignite, stop
from scripts import stage9c_three_hour_soak_http_gate as gate


def denied(conn, job, identity, reason):
    try:
        gate.admit_physical_start(conn, job, identity)
    except RuntimeError as exc:
        if reason not in str(exc):
            raise
    else:
        raise RuntimeError(f"gate accepted forbidden state: {reason}")


def main():
    e = engine()
    with e.connect() as conn:
        tx = conn.begin()
        try:
            ids = cohort_ids(conn)
            if conn.execute(text("SELECT count(*) FROM soak_runs")).scalar_one():
                raise RuntimeError("existing soak run")
            create_prepared_run(conn, ids)
            jobs = None
            ci = SimpleNamespace(hostname="tcou", lane="background",
                                 collector_uuid=UUIDS["tcou"],
                                 collector_name=RUN+":tcou",
                                 egress_key=RUN+":tcou")
            fake = SimpleNamespace(job_id=-1, soldier_id=ids[0])
            denied(conn, fake, ci, "run not running")
            ignite(conn, ids)
            jobs = admit_round(conn, ids, 1)
            job = SimpleNamespace(job_id=jobs[0], soldier_id=ids[0])
            gate.admit_physical_start(conn, job, ci)
            denied(conn, fake, ci, "job not attributed")
            denied(conn, job, SimpleNamespace(**{**vars(ci), "hostname":"unknown"}), "unexpected site")
            # Shrink code-side threshold to 0 to exercise each budget rejection
            # without manufacturing hundreds of fake event records.
            original_site = gate.SITE_ATTEMPTS
            gate.SITE_ATTEMPTS = 0
            try:
                denied(conn, job, ci, "altered run budget")
            finally:
                gate.SITE_ATTEMPTS = original_site
            conn.execute(text("""
                UPDATE soak_runs SET deadline_at=clock_timestamp()-interval '1 second'
                WHERE run_id=:run
            """), {"run":RUN_ID})
            denied(conn, job, ci, "deadline expired")
            conn.execute(text("""
                UPDATE soak_runs SET deadline_at=clock_timestamp()+interval '3 hours'
                WHERE run_id=:run
            """), {"run":RUN_ID})
            stop(conn, "test stop")
            denied(conn, job, ci, "run not running")
            print("HTTP GATE PASS running=accepted unattributed=blocked unknown_site=blocked budget_tamper=blocked deadline=blocked stop=blocked")
        finally:
            tx.rollback()
    with e.connect() as conn:
        counts={table:conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
                for table in ("soak_runs","soak_rounds","soak_round_jobs","collection_jobs")}
        if any(counts.values()):
            raise RuntimeError(f"rollback residue {counts}")
        print("HTTP GATE ROLLBACK PASS",counts)


if __name__=="__main__":
    main()
