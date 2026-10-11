"""D2 soak round-ledger transaction primitives.

No automatic ignition or HTTP. All mutating calls require an explicit caller
transaction and verified isolated D2 connection. The PostgreSQL ledger is
authoritative; a JSON manifest is only an operator-facing checkpoint.
"""
from __future__ import annotations

from datetime import timedelta
from hashlib import sha256
from typing import Sequence

from sqlalchemy import text
from sqlalchemy.engine import Connection

from bf4ps.collection_jobs import enqueue_job

RUN_ID = "bf4ps-d2-three-hour-soak-20261011-v1"
EXPECTED_REV = "0006_stage9c_soak_round_ledger"
BASELINE_EVENT = 109
MAX_ATTEMPTS = 108
SITE_ATTEMPTS = 36
ROUNDS = 12
ROUND_SECONDS = 900


def guard(conn: Connection) -> None:
    row = conn.execute(text("""
        SELECT current_database(), current_user, pg_is_in_recovery(),
               current_setting('transaction_read_only')
    """)).one()
    rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    if tuple(row) != ("bf4ps_scratch_stage9c_d2", "bf4ps_stage9c_d2", False, "off"):
        raise RuntimeError("REFUSING unexpected DB, role, primary or read-only state")
    if rev != EXPECTED_REV:
        raise RuntimeError(f"REFUSING schema revision {rev}")


def digest_cohort(ids: Sequence[int]) -> str:
    ids = tuple(sorted(ids))
    if len(ids) != 9 or len(set(ids)) != 9 or any(x <= 0 for x in ids):
        raise RuntimeError("invalid nine-soldier cohort")
    return sha256(",".join(map(str, ids)).encode()).hexdigest()


def create_prepared_run(conn: Connection, ids: Sequence[int]) -> None:
    """Idempotent only for the exact same immutable prepared run."""
    guard(conn)
    digest = digest_cohort(ids)
    conn.execute(text("SELECT pg_advisory_xact_lock(90841011, 3)"))
    row = conn.execute(text("""
        SELECT cohort_digest, baseline_event_id, attempt_ceiling,
               site_attempt_ceiling, state, start_at, deadline_at
        FROM soak_runs WHERE run_id=:run FOR UPDATE
    """), {"run": RUN_ID}).one_or_none()
    if row is not None:
        if tuple(row) != (digest, BASELINE_EVENT, MAX_ATTEMPTS,
                          SITE_ATTEMPTS, "prepared", None, None):
            raise RuntimeError("existing run differs or already ignited")
        return
    if conn.execute(text("SELECT count(*) FROM collection_jobs")).scalar_one():
        raise RuntimeError("queue not empty")
    if conn.execute(text("SELECT coalesce(max(event_id),0) FROM collection_events")).scalar_one() != BASELINE_EVENT:
        raise RuntimeError("event baseline changed")
    conn.execute(text("""
        INSERT INTO soak_runs(run_id,cohort_digest,baseline_event_id,
                              attempt_ceiling,site_attempt_ceiling,state)
        VALUES(:run,:digest,:base,:ceiling,:site,'prepared')
    """), {"run": RUN_ID, "digest": digest, "base": BASELINE_EVENT,
           "ceiling": MAX_ATTEMPTS, "site": SITE_ATTEMPTS})


def admit_round(conn: Connection, ids: Sequence[int], number: int) -> list[int]:
    """Atomically enqueue nine jobs and persist their permanent round mapping.

    Requires explicit ignition recorded in soak_runs and round eligibility.
    Refuses to recover ambiguous or incomplete earlier rounds automatically.
    """
    guard(conn)
    if not 1 <= number <= ROUNDS:
        raise RuntimeError("round out of range")
    digest = digest_cohort(ids)
    conn.execute(text("SELECT pg_advisory_xact_lock(90841011, 3)"))
    run = conn.execute(text("""
        SELECT cohort_digest,baseline_event_id,attempt_ceiling,state,
               start_at,deadline_at
        FROM soak_runs WHERE run_id=:run FOR UPDATE
    """), {"run": RUN_ID}).one_or_none()
    if run is None or run.cohort_digest != digest or run.baseline_event_id != BASELINE_EVENT:
        raise RuntimeError("run/cohort mismatch")
    if run.state != "running" or run.start_at is None or run.deadline_at is None:
        raise RuntimeError("run not ignited")
    now = conn.execute(text("SELECT clock_timestamp()")).scalar_one()
    eligible = run.start_at + timedelta(seconds=(number - 1) * ROUND_SECONDS)
    if not eligible <= now < run.deadline_at:
        raise RuntimeError("round outside scheduled window")
    if conn.execute(text("""
        SELECT 1 FROM soak_rounds WHERE run_id=:run AND round_number=:n
    """), {"run": RUN_ID, "n": number}).first():
        raise RuntimeError("round already admitted or planned")
    previous = conn.execute(text("""
        SELECT round_number,state FROM soak_rounds
        WHERE run_id=:run ORDER BY round_number DESC LIMIT 1
    """), {"run": RUN_ID}).one_or_none()
    if number == 1:
        if previous is not None:
            raise RuntimeError("unexpected previous round")
    elif previous is None or previous.round_number != number - 1 or previous.state != "completed":
        raise RuntimeError("previous round not reconciled")
    if conn.execute(text("SELECT count(*) FROM collection_jobs")).scalar_one():
        raise RuntimeError("queue not empty")
    # Conservatively refuse further admission unless all earlier HTTP starts
    # and in-flight reservations leave room for all nine new requests.
    used = conn.execute(text("""
        SELECT count(DISTINCT (job_id,attempt_number)) FROM collection_events
        WHERE event_id > :base AND resource='detailed'
          AND event_type='collection_attempt_started'
    """), {"base": BASELINE_EVENT}).scalar_one()
    if used + 9 > MAX_ATTEMPTS:
        raise RuntimeError("insufficient remaining request budget")
    conn.execute(text("""
        INSERT INTO soak_rounds(run_id,round_number,eligible_at,state,enqueued_at)
        VALUES(:run,:n,:eligible,'enqueued',:now)
    """), {"run": RUN_ID, "n": number, "eligible": eligible, "now": now})
    jobs = []
    for sid in sorted(ids):
        jid = enqueue_job(conn, soldier_id=sid, resource="detailed",
                          lane="background", priority_class="bootstrap",
                          reason=f"{RUN_ID}:round-{number:02d}")
        conn.execute(text("""
            INSERT INTO soak_round_jobs(run_id,round_number,soldier_id,job_id)
            VALUES(:run,:n,:sid,:jid)
        """), {"run": RUN_ID, "n": number, "sid": sid, "jid": jid})
        jobs.append(jid)
    return jobs
