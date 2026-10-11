"""D2-only final-slot concurrency integration test (NO HTTP).

This probe intentionally uses committed fixture rows so two PostgreSQL
connections can observe them. It MUST be run only on the isolated D2
database with an empty queue/soak ledger; finally removes every fixture
row in dependency order. If cleanup fails, STOP and inspect D2.
"""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace
from sqlalchemy import text
from scripts.stage9c_three_site_live_ignition import engine, RUN, UUIDS
from scripts.stage9c_three_hour_soak_cohort import cohort_ids
from scripts.stage9c_three_hour_soak_ledger import (
    RUN_ID, BASELINE_EVENT, create_prepared_run, admit_round,
)
from scripts.stage9c_three_hour_soak_lifecycle import ignite
from scripts.stage9c_three_hour_soak_http_gate import admit_physical_start

def ci(site):
    return SimpleNamespace(hostname=site,lane="background",
        collector_uuid=UUIDS[site],collector_name=RUN+":"+site,
        egress_key=RUN+":"+site)

def worker(e, job, start):
    start.wait(timeout=10)
    with e.begin() as conn:
        admit_physical_start(conn,job,ci("tcou"))
        # This event is the physical-start budget reservation.
        conn.execute(text("""
            INSERT INTO collection_events
              (collector_uuid,collector_name_snapshot,hostname_snapshot,
               egress_key_snapshot,job_id,soldier_id,resource,lane,
               event_type,attempt_number,metadata)
            VALUES (:uuid,:name,'tcou',:egress,:job,:soldier,'detailed',
                    'background','collection_attempt_started',:attempt,
                    '{"physical_request":true}'::jsonb)
        """),{"uuid":UUIDS["tcou"],"name":RUN+":tcou",
              "egress":RUN+":tcou","job":job.job_id,
              "soldier":job.soldier_id,"attempt":job.attempt_count})
    return "accepted"

def main():
    e=engine()
    baseline=None
    with e.connect() as conn:
        ids=cohort_ids(conn)
        if conn.execute(text("SELECT count(*) FROM soak_runs")).scalar_one():
            raise RuntimeError("existing soak ledger")
        if conn.execute(text("SELECT count(*) FROM collection_jobs")).scalar_one():
            raise RuntimeError("queue not empty")
        baseline=conn.execute(text("SELECT coalesce(max(event_id),0) FROM collection_events")).scalar_one()
        if baseline != BASELINE_EVENT:
            raise RuntimeError("unexpected event baseline")
    fixture_jobs=[]
    try:
        with e.begin() as conn:
            create_prepared_run(conn,ids)
            ignite(conn,ids)
            fixture_jobs=admit_round(conn,ids,1)
            # 35 prior tcou starts; exactly one slot remains for tcou.
            conn.execute(text("""
                INSERT INTO collection_events
                  (collector_uuid,collector_name_snapshot,hostname_snapshot,
                   egress_key_snapshot,job_id,soldier_id,resource,lane,
                   event_type,attempt_number,metadata)
                SELECT :uuid,:name,'tcou',:egress,:job,:soldier,'detailed',
                       'background','collection_attempt_started',
                       generate_series(100,134),'{"physical_request":true}'::jsonb
            """),{"uuid":UUIDS["tcou"],"name":RUN+":tcou",
                  "egress":RUN+":tcou","job":fixture_jobs[0],"soldier":ids[0]})
        jobs=[SimpleNamespace(job_id=fixture_jobs[i],soldier_id=ids[i],
                              attempt_count=1) for i in (0,1)]
        start=Event()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(worker,e,job,start) for job in jobs]
            start.set()
            results=[]
            for future in futures:
                try:
                    results.append(future.result(timeout=20))
                except RuntimeError as exc:
                    if "physical attempt budget exhausted" not in str(exc):
                        raise
                    results.append("blocked")
        if sorted(results)!=["accepted","blocked"]:
            raise RuntimeError(f"unexpected race results {results}")
        print("FINAL SLOT RACE PASS accepted=1 blocked=1")
    finally:
        # Fixture cleanup must be scoped by the exact run's job IDs.
        with e.begin() as conn:
            if fixture_jobs:
                conn.execute(text("""
                    DELETE FROM collection_events
                    WHERE event_id>:base AND job_id=ANY(:jobs)
                """),{"base":baseline,"jobs":fixture_jobs})
                conn.execute(text("DELETE FROM collection_jobs WHERE job_id=ANY(:jobs)"),
                             {"jobs":fixture_jobs})
                conn.execute(text("DELETE FROM soak_round_jobs WHERE run_id=:run"),{"run":RUN_ID})
                conn.execute(text("DELETE FROM soak_rounds WHERE run_id=:run"),{"run":RUN_ID})
                conn.execute(text("DELETE FROM soak_runs WHERE run_id=:run"),{"run":RUN_ID})
    with e.connect() as conn:
        if conn.execute(text("SELECT count(*) FROM soak_runs")).scalar_one():
            raise RuntimeError("fixture cleanup incomplete")
        if conn.execute(text("SELECT count(*) FROM collection_jobs")).scalar_one():
            raise RuntimeError("queue cleanup incomplete")
        print("FINAL SLOT RACE CLEANUP PASS")

if __name__=="__main__":
    main()
