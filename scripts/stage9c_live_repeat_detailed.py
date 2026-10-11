"""Repeat one live detailed-stat collection through the real BF4PS collector.

Requires BF4PS_STAGE9C_INTEGRATION_URL and the retained first-live fixture.
Never targets production. At most one newly admitted detailed attempt.
"""
from __future__ import annotations

import os
from sqlalchemy import create_engine, text
from bf4ps.collection_jobs import enqueue_job
from bf4ps.detailed_collector import CollectorIdentity, CollectedJob, FailedJob, collect_one_detailed_job

EXPECTED_DB = "bf4ps_scratch_stage9c_integration"
EXPECTED_USER = "bf4ps_stage9c_integration"
EXPECTED_REVISION = "0004_stage9c_supervision_runs"
EXPECTED_PERSONA = 236753552
EXPECTED_COLLECTOR = "live-persistence-validation-tcou"


def main() -> None:
    url = os.environ["BF4PS_STAGE9C_INTEGRATION_URL"]
    engine = create_engine(url, pool_pre_ping=True)
    with engine.connect() as conn:
        db, user, recovery, read_only = conn.execute(text(
            "SELECT current_database(), current_user, pg_is_in_recovery(), current_setting('transaction_read_only')"
        )).one()
        revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        if (db, user, recovery, read_only, revision) != (
            EXPECTED_DB, EXPECTED_USER, False, "off", EXPECTED_REVISION
        ):
            raise RuntimeError("refusing unexpected database, role, recovery, read-only or revision")
        if conn.execute(text("SELECT count(*) FROM collection_jobs")).scalar_one() != 0:
            raise RuntimeError("refusing nonempty collection queue")
        if conn.execute(text("SELECT count(*) FROM collectors")).scalar_one() != 1:
            raise RuntimeError("refusing unexpected collector inventory")
        collector = conn.execute(text("""
            SELECT collector_uuid, collector_name, hostname, egress_key, lane, enabled, drained,
                   retired_at, current_job_id
            FROM collectors WHERE collector_name=:name
        """), {"name": EXPECTED_COLLECTOR}).mappings().one()
        if not (
            collector["hostname"] == "tcou"
            and collector["egress_key"] == "tcou-live-validation"
            and collector["lane"] == "background"
            and collector["enabled"] and not collector["drained"]
            and collector["retired_at"] is None and collector["current_job_id"] is None
        ):
            raise RuntimeError("refusing unexpected collector state")
        soldier = conn.execute(text("""
            SELECT s.soldier_id, cs.detailed_state, d.source_fetched_at
            FROM soldiers s JOIN collection_state cs USING (soldier_id)
            JOIN detailed_stats_current d USING (soldier_id)
            WHERE s.persona_id=:persona AND s.platform='pc'
        """), {"persona": EXPECTED_PERSONA}).mappings().one()
        if soldier["detailed_state"] != "success":
            raise RuntimeError("refusing missing previous successful collection")
        baseline = conn.execute(text("""
            SELECT coalesce(max(event_id),0) FROM collection_events
        """)).scalar_one()
        old_history = conn.execute(text("""
            SELECT count(*) FROM detailed_stats_history WHERE soldier_id=:id
        """), {"id": soldier["soldier_id"]}).scalar_one()
        old_current = soldier["source_fetched_at"]
        print(f"PREFLIGHT PASS db={db} revision={revision} soldier={soldier['soldier_id']} "
              f"baseline_event={baseline} history={old_history}", flush=True)
    identity = CollectorIdentity(
        collector_uuid=collector["collector_uuid"],
        collector_name=collector["collector_name"],
        hostname=collector["hostname"],
        egress_key=collector["egress_key"],
        lane=collector["lane"],
    )
    with engine.begin() as conn:
        enqueue_job(
            conn, soldier_id=soldier["soldier_id"], resource="detailed",
            lane="background", priority_class="bootstrap",
            reason="authorized_live_repeat_detailed_validation",
        )
    result = collect_one_detailed_job(
        engine, identity=identity, request_interval_seconds=10.0,
        allowed_soldier_ids=[soldier["soldier_id"]], max_total_attempts=1,
        attempts_after_event_id=baseline,
        attempt_ceiling_resources=["detailed"], enforce_production_budget=True,
        timeout_seconds=15.0, lease_seconds=120, retry_after_seconds=3600,
    )
    with engine.connect() as conn:
        events = conn.execute(text("""
            SELECT event_type, result FROM collection_events
            WHERE soldier_id=:id AND event_id>:baseline ORDER BY event_id
        """), {"id":soldier["soldier_id"],"baseline":baseline}).all()
        current = conn.execute(text("""
            SELECT source_fetched_at,kills,deaths FROM detailed_stats_current WHERE soldier_id=:id
        """), {"id":soldier["soldier_id"]}).one()
        history = conn.execute(text("""
            SELECT count(*) FROM detailed_stats_history WHERE soldier_id=:id
        """), {"id":soldier["soldier_id"]}).scalar_one()
        state = conn.execute(text("""
            SELECT detailed_state FROM collection_state WHERE soldier_id=:id
        """), {"id":soldier["soldier_id"]}).scalar_one()
        jobs = conn.execute(text("""
            SELECT count(*) FROM collection_jobs WHERE soldier_id=:id
        """), {"id":soldier["soldier_id"]}).scalar_one()
    print(f"RESULT={result!r} events={events} current={current} "
          f"history={history} previous_history={old_history} state={state} jobs={jobs}",flush=True)
    if isinstance(result, CollectedJob):
        assert state == "success" and jobs == 0
        assert [e[0] for e in events] == ["collection_attempt_started","collection_success"]
        assert current.source_fetched_at > old_current
        assert history == old_history + int(result.history_appended)
        print("REPEAT LIVE DETAILED PERSISTENCE PASS",flush=True)
    elif isinstance(result, FailedJob):
        print("REPEAT FETCH FAILED (durably recorded); inspect before retry",flush=True)
        raise SystemExit(2)
    else:
        raise RuntimeError("no eligible job claimed; inspect budget and queue")


if __name__ == "__main__":
    main()
