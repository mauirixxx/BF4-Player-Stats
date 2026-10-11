"""Rollback-only integration tests for Stage 9C D2 round reconciliation.

Exercise incomplete, successful, and anomalous event states against real
PostgreSQL. All inserted rows are rolled back; no HTTP calls are made.
"""
from __future__ import annotations

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
                raise RuntimeError("existing soak run")
            create_prepared_run(conn, ids)
            conn.execute(text("""
                UPDATE soak_runs SET state='running',
                  start_at=clock_timestamp()-interval '1 minute',
                  deadline_at=clock_timestamp()+interval '3 hours'
                WHERE run_id=:run
            """), {"run": RUN_ID})
            jobs = admit_round(conn, ids, 1)
            first = inspect_round(conn, 1)
            if not first["any_queued"] or first["all_success"] or first["anomalies"]:
                raise RuntimeError("queued round inspection incorrect")
            incomplete = reconcile(conn, 1)
            if incomplete["state"] != "enqueued":
                raise RuntimeError("incomplete round was marked completed")
            # Simulate durable collection outcomes, preserving real collector
            # identity fields from the registered D2 collectors.
            collector = conn.execute(text("""
                SELECT collector_uuid,collector_name,hostname,egress_key
                FROM collectors WHERE hostname='tcou'
            """)).mappings().one()
            for sid, jid in zip(ids, jobs):
                conn.execute(text("DELETE FROM collection_jobs WHERE job_id=:job"),
                             {"job": jid})
                for kind in ("collection_attempt_started", "collection_success"):
                    conn.execute(text("""
                        INSERT INTO collection_events
                          (occurred_at,collector_uuid,collector_name_snapshot,
                           hostname_snapshot,egress_key_snapshot,job_id,
                           soldier_id,resource,lane,event_type,attempt_number,
                           result)
                        VALUES (clock_timestamp(),:uuid,:name,:host,:egress,
                                :job,:soldier,'detailed','background',:kind,1,
                                'success')
                    """), {"uuid": collector["collector_uuid"],
                           "name": collector["collector_name"],
                           "host": collector["hostname"],
                           "egress": collector["egress_key"],
                           "job": jid, "soldier": sid, "kind": kind})
            complete = reconcile(conn, 1)
            if complete["state"] != "completed" or not complete["all_success"]:
                raise RuntimeError("successful round not reconciled")
            again = reconcile(conn, 1)
            if again["state"] != "completed":
                raise RuntimeError("repeated reconciliation not idempotent")
            print("RECONCILIATION PASS incomplete=held complete=accepted repeat=idempotent")
        finally:
            tx.rollback()
    with e.connect() as conn:
        counts = {name: conn.execute(text(f"SELECT count(*) FROM {name}")).scalar_one()
                  for name in ("soak_runs", "soak_rounds", "soak_round_jobs", "collection_jobs")}
        if any(counts.values()):
            raise RuntimeError(f"rollback residue: {counts}")
        print("RECONCILIATION ROLLBACK PASS", counts)


if __name__ == "__main__":
    main()
