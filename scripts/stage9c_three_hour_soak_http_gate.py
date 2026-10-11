"""D2-only serialized physical-start admission, inside collector start transaction.

Must be passed as pre_http_admission to collect_one_detailed_job.
Never call independently as an authorization to issue HTTP.
"""
from sqlalchemy import text
from scripts.stage9c_three_hour_soak_ledger import (
    RUN_ID, BASELINE_EVENT, MAX_ATTEMPTS, SITE_ATTEMPTS, guard,
)

SITES = frozenset(("tcou", "kah-01", "hnl-01"))


def admit_physical_start(conn, job, identity):
    guard(conn)
    if identity.hostname not in SITES or identity.lane != "background":
        raise RuntimeError("SOAK BLOCK: unexpected site/lane")
    conn.execute(text("SELECT pg_advisory_xact_lock(90841011,3)"))
    run = conn.execute(text("""
        SELECT state,deadline_at,attempt_ceiling,site_attempt_ceiling,
               baseline_event_id FROM soak_runs WHERE run_id=:run FOR UPDATE
    """), {"run": RUN_ID}).one_or_none()
    if run is None or run.state != "running" or run.deadline_at is None:
        raise RuntimeError("SOAK BLOCK: run not running")
    if conn.execute(text("SELECT clock_timestamp()")).scalar_one() >= run.deadline_at:
        raise RuntimeError("SOAK BLOCK: deadline expired")
    if (run.attempt_ceiling != MAX_ATTEMPTS or
        run.site_attempt_ceiling != SITE_ATTEMPTS or
        run.baseline_event_id != BASELINE_EVENT):
        raise RuntimeError("SOAK BLOCK: altered run budget")
    registered = conn.execute(text("""
        SELECT 1 FROM collectors
        WHERE collector_uuid=:uuid AND hostname=:host
          AND collector_name=:name AND egress_key=:egress
          AND lane='background' AND enabled AND NOT drained
          AND retired_at IS NULL
    """), {"uuid": identity.collector_uuid, "host": identity.hostname,
           "name": identity.collector_name,
           "egress": identity.egress_key}).first()
    if registered is None:
        raise RuntimeError("SOAK BLOCK: unregistered collector identity")
    attributed = conn.execute(text("""
        SELECT 1 FROM soak_round_jobs j
        JOIN soak_rounds r USING(run_id,round_number)
        WHERE j.run_id=:run AND j.job_id=:job
          AND j.soldier_id=:soldier AND r.state='enqueued'
    """), {"run": RUN_ID, "job": job.job_id, "soldier": job.soldier_id}).first()
    if attributed is None:
        raise RuntimeError("SOAK BLOCK: job not attributed to active round")
    counts = conn.execute(text("""
        SELECT count(DISTINCT (job_id,attempt_number)) AS total,
               count(DISTINCT (job_id,attempt_number))
                 FILTER (WHERE hostname_snapshot=:site) AS site
        FROM collection_events
        WHERE event_id>:base AND resource='detailed'
          AND event_type='collection_attempt_started'
    """), {"base": BASELINE_EVENT, "site": identity.hostname}).one()
    if counts.total >= MAX_ATTEMPTS or counts.site >= SITE_ATTEMPTS:
        raise RuntimeError("SOAK BLOCK: physical attempt budget exhausted")
