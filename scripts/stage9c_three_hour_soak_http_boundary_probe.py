"""Rollback-only exact site/global HTTP-start boundary tests on isolated D2.

Uses synthetic collection_attempt_started events within one uncommitted
transaction. Tests the real 36/site and 108/global thresholds without HTTP.
"""
from types import SimpleNamespace
from sqlalchemy import text
from scripts.stage9c_three_site_live_ignition import engine, RUN, UUIDS
from scripts.stage9c_three_hour_soak_cohort import cohort_ids
from scripts.stage9c_three_hour_soak_ledger import RUN_ID, create_prepared_run, admit_round
from scripts.stage9c_three_hour_soak_lifecycle import ignite
from scripts.stage9c_three_hour_soak_http_gate import admit_physical_start


def identity(site):
    return SimpleNamespace(hostname=site,lane="background",
        collector_uuid=UUIDS[site],collector_name=RUN+":"+site,
        egress_key=RUN+":"+site)


def denied(conn,job,ci):
    try:
        admit_physical_start(conn,job,ci)
    except RuntimeError as exc:
        if "physical attempt budget exhausted" not in str(exc):
            raise
    else:
        raise RuntimeError("physical gate exceeded budget")


def insert_starts(conn,job,site,count,offset):
    ci=identity(site)
    conn.execute(text("""
        INSERT INTO collection_events
          (collector_uuid,collector_name_snapshot,hostname_snapshot,
           egress_key_snapshot,job_id,soldier_id,resource,lane,
           event_type,attempt_number,metadata)
        SELECT :uuid,:name,:site,:egress,:job,:soldier,'detailed',
               'background','collection_attempt_started',
               generate_series(CAST(:lo AS integer),CAST(:hi AS integer)),jsonb_build_object('physical_request',true)
    """),{"uuid":ci.collector_uuid,"name":ci.collector_name,
           "site":site,"egress":ci.egress_key,"job":job.job_id,
           "soldier":job.soldier_id,"lo":offset+1,"hi":offset+count})


def main():
    e=engine()
    with e.connect() as conn:
        tx=conn.begin()
        try:
            ids=cohort_ids(conn)
            if conn.execute(text("SELECT count(*) FROM soak_runs")).scalar_one():
                raise RuntimeError("existing run")
            create_prepared_run(conn,ids)
            ignite(conn,ids)
            jobs=admit_round(conn,ids,1)
            job=SimpleNamespace(job_id=jobs[0],soldier_id=ids[0])
            insert_starts(conn,job,"tcou",35,0)
            admit_physical_start(conn,job,identity("tcou"))
            insert_starts(conn,job,"tcou",1,35)
            denied(conn,job,identity("tcou"))
            # At 107 total, kah still has 36 slots available locally.
            insert_starts(conn,job,"hnl-01",36,100)
            insert_starts(conn,job,"kah-01",36,200)
            # total is now 108: tcou36 + hnl36 + kah36
            denied(conn,job,identity("kah-01"))
            print("HTTP BOUNDARY PASS site35=allowed site36=blocked global108=blocked")
        finally:
            tx.rollback()
    with e.connect() as conn:
        counts={t:conn.execute(text(f"SELECT count(*) FROM {t}")).scalar_one()
                for t in ("soak_runs","soak_rounds","soak_round_jobs","collection_jobs")}
        if any(counts.values()):
            raise RuntimeError(f"rollback residue: {counts}")
        print("HTTP BOUNDARY ROLLBACK PASS",counts)


if __name__=="__main__":
    main()
