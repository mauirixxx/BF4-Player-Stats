"""Rollback-only anomaly tests for D2 three-hour soak reconciliation.

Covers absent success and duplicate success events, including the case where
a queue row has disappeared. All changes roll back; no HTTP.
"""
from sqlalchemy import text
from scripts.stage9c_three_site_live_ignition import engine
from scripts.stage9c_three_hour_soak_cohort import cohort_ids
from scripts.stage9c_three_hour_soak_ledger import RUN_ID, create_prepared_run, admit_round
from scripts.stage9c_three_hour_soak_reconcile import inspect_round, reconcile


def main():
    e = engine()
    with e.connect() as conn:
        tx = conn.begin()
        try:
            ids = cohort_ids(conn)
            if conn.execute(text("SELECT count(*) FROM soak_runs")).scalar_one():
                raise RuntimeError("existing run")
            create_prepared_run(conn, ids)
            conn.execute(text("""
                UPDATE soak_runs SET state='running',
                  start_at=clock_timestamp()-interval '1 minute',
                  deadline_at=clock_timestamp()+interval '3 hours'
                WHERE run_id=:run
            """), {"run": RUN_ID})
            jobs = admit_round(conn, ids, 1)
            collector = conn.execute(text("""
                SELECT collector_uuid,collector_name,hostname,egress_key
                FROM collectors WHERE hostname='tcou'
            """)).mappings().one()
            def event(jid, sid, kind):
                conn.execute(text("""
                    INSERT INTO collection_events
                      (occurred_at,collector_uuid,collector_name_snapshot,
                       hostname_snapshot,egress_key_snapshot,job_id,soldier_id,
                       resource,lane,event_type,attempt_number,result)
                    VALUES(clock_timestamp(),:uuid,:name,:host,:egress,:job,:sid,
                           'detailed','background',:kind,1,'success')
                """), {"uuid":collector["collector_uuid"],
                       "name":collector["collector_name"],
                       "host":collector["hostname"],
                       "egress":collector["egress_key"],
                       "job":jid,"sid":sid,"kind":kind})
            # Simulate disappearing queue row with no success.
            conn.execute(text("DELETE FROM collection_jobs WHERE job_id=:job"),
                         {"job":jobs[0]})
            missing = inspect_round(conn, 1)
            if jobs[0] not in missing["anomalies"]:
                raise RuntimeError("missing success not detected")
            try:
                reconcile(conn, 1)
            except RuntimeError as exc:
                if "missing/duplicate success" not in str(exc):
                    raise
            else:
                raise RuntimeError("missing success was accepted")
            # Repair simulated missing event and add two successes for job 2.
            event(jobs[0], ids[0], "collection_attempt_started")
            event(jobs[0], ids[0], "collection_success")
            event(jobs[1], ids[1], "collection_attempt_started")
            event(jobs[1], ids[1], "collection_success")
            event(jobs[1], ids[1], "collection_success")
            duplicate = inspect_round(conn, 1)
            if jobs[1] not in duplicate["anomalies"]:
                raise RuntimeError("duplicate success not detected")
            try:
                reconcile(conn, 1)
            except RuntimeError as exc:
                if "missing/duplicate success" not in str(exc):
                    raise
            else:
                raise RuntimeError("duplicate success was accepted")
            print("ANOMALY PASS missing_success=rejected duplicate_success=rejected")
        finally:
            tx.rollback()
    with e.connect() as conn:
        counts = {table:conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
                  for table in ("soak_runs","soak_rounds","soak_round_jobs","collection_jobs")}
        if any(counts.values()):
            raise RuntimeError(f"rollback residue: {counts}")
        print("ANOMALY ROLLBACK PASS", counts)


if __name__ == "__main__":
    main()
