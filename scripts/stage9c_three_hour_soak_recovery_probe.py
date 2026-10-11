"""Rollback-only D2 lease-loss recovery and atomic HTTP-budget proof. No HTTP."""
from sqlalchemy import text
from bf4ps.collection_jobs import claim_next_job,mark_job_running,renew_lease
from scripts.stage9c_three_site_live_ignition import engine,RUN,UUIDS
from scripts.stage9c_three_hour_soak_cohort import cohort_ids
from scripts.stage9c_three_hour_soak_ledger import RUN_ID,BASELINE_EVENT,create_prepared_run,admit_round
from scripts.stage9c_three_hour_soak_lifecycle import ignite
from scripts.stage9c_three_hour_soak_http_gate import admit_physical_start
from types import SimpleNamespace

def identity(site):
    return SimpleNamespace(hostname=site,lane="background",collector_uuid=UUIDS[site],
        collector_name=RUN+":"+site,egress_key=RUN+":"+site)

def claim(conn,site,ids):
    return claim_next_job(conn,collector_uuid=UUIDS[site],lane="background",
        resource="detailed",lease_seconds=120,allowed_soldier_ids=ids,
        max_total_attempts=108,attempts_after_event_id=BASELINE_EVENT,
        attempt_ceiling_resources=["detailed"])

def main():
    e=engine()
    with e.connect() as conn:
        tx=conn.begin()
        try:
            ids=cohort_ids(conn)
            if conn.execute(text("SELECT count(*) FROM soak_runs")).scalar_one():
                raise RuntimeError("existing soak run")
            create_prepared_run(conn,ids)
            ignite(conn,ids)
            jobs=admit_round(conn,ids,1)
            old=claim(conn,"kah-01",ids)
            if old is None or not mark_job_running(conn,old):
                raise RuntimeError("victim claim failed")
            admit_physical_start(conn,old,identity("kah-01"))
            conn.execute(text("""
                INSERT INTO collection_events
                  (collector_uuid,collector_name_snapshot,hostname_snapshot,
                   egress_key_snapshot,job_id,soldier_id,resource,lane,
                   event_type,attempt_number,metadata)
                VALUES (:uuid,:name,'kah-01',:egress,:job,:sid,'detailed',
                        'background','collection_attempt_started',1,
                        jsonb_build_object('physical_request',true))
            """),{"uuid":UUIDS["kah-01"],"name":RUN+":kah-01",
                  "egress":RUN+":kah-01","job":old.job_id,"sid":old.soldier_id})
            conn.execute(text("""
                UPDATE collection_jobs SET lease_expires_at=now()-interval '1 second'
                WHERE job_id=:job
            """),{"job":old.job_id})
            if renew_lease(conn,old,lease_seconds=120):
                raise RuntimeError("expired victim renewed")
            recovered=claim(conn,"hnl-01",ids)
            if recovered is None or recovered.job_id!=old.job_id or recovered.attempt_count!=2:
                raise RuntimeError(f"recovery mismatch {recovered}")
            if not mark_job_running(conn,recovered):
                raise RuntimeError("rescuer running transition failed")
            if renew_lease(conn,old,lease_seconds=120):
                raise RuntimeError("stale owner renewed")
            admit_physical_start(conn,recovered,identity("hnl-01"))
            counts=conn.execute(text("""
                SELECT count(DISTINCT (job_id,attempt_number)) FROM collection_events
                WHERE event_id>:base AND event_type='collection_attempt_started'
            """),{"base":BASELINE_EVENT}).scalar_one()
            if counts!=1:
                raise RuntimeError(f"unexpected physical attempt count {counts}")
            print("RECOVERY PASS expired_owner=blocked stale_owner=blocked rescuer_attempt=2 durable_physical_starts=1")
        finally:
            tx.rollback()
    with e.connect() as conn:
        counts={t:conn.execute(text(f"SELECT count(*) FROM {t}")).scalar_one()
                for t in ("soak_runs","soak_rounds","soak_round_jobs","collection_jobs")}
        if any(counts.values()):
            raise RuntimeError(f"rollback residue {counts}")
        print("RECOVERY ROLLBACK PASS",counts)

if __name__=="__main__":
    main()
