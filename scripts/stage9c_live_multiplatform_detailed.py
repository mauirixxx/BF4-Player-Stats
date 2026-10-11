"""Bounded three-platform live detailed cohort using the current collector path.

Only the isolated Stage 9C integration scratch database is accepted. The two
non-PC personas are historical Phase 1 verified candidates, not invented IDs.
A maximum of two newly admitted attempts is shared across this run's cohort.
"""
from __future__ import annotations

import os
from sqlalchemy import create_engine, text

from bf4ps.collection_jobs import enqueue_job
from bf4ps.detailed_collector import (
    CollectorIdentity, CollectedJob, FailedJob, collect_one_detailed_job,
)

COHORT = (
    ("xSilverMystx", 303498475, "ps4"),
    ("S0UL OF STEEL", 928420744, "xboxone"),
)
EXPECTED_DB = "bf4ps_scratch_stage9c_integration"
EXPECTED_ROLE = "bf4ps_stage9c_integration"
EXPECTED_REVISION = "0004_stage9c_supervision_runs"
EXPECTED_COLLECTOR = "live-persistence-validation-tcou"


def main():
    engine = create_engine(os.environ["BF4PS_STAGE9C_INTEGRATION_URL"], pool_pre_ping=True)
    with engine.connect() as conn:
        target = conn.execute(text(
            "SELECT current_database(),current_user,pg_is_in_recovery(),"
            "current_setting('transaction_read_only')"
        )).one()
        rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        if tuple(target) != (EXPECTED_DB, EXPECTED_ROLE, False, "off") or rev != EXPECTED_REVISION:
            raise RuntimeError("refusing unexpected database or migration revision")
        if conn.execute(text("SELECT count(*) FROM collection_jobs")).scalar_one() != 0:
            raise RuntimeError("refusing nonempty queue")
        if conn.execute(text("SELECT count(*) FROM collectors")).scalar_one() != 1:
            raise RuntimeError("refusing unexpected collector inventory")
        collector = conn.execute(text("""
            SELECT collector_uuid,collector_name,hostname,egress_key,lane,enabled,drained,
                   retired_at,current_job_id FROM collectors WHERE collector_name=:name
        """), {"name":EXPECTED_COLLECTOR}).mappings().one()
        if not (collector["hostname"] == "tcou" and
                collector["egress_key"] == "tcou-live-validation" and
                collector["lane"] == "background" and collector["enabled"] and
                not collector["drained"] and collector["retired_at"] is None and
                collector["current_job_id"] is None):
            raise RuntimeError("refusing unexpected collector state")
        for name, persona, platform in COHORT:
            exists = conn.execute(text("""
                SELECT 1 FROM soldiers WHERE persona_id=:persona AND platform=:platform
            """), {"persona":persona,"platform":platform}).one_or_none()
            if exists is not None:
                raise RuntimeError(f"refusing existing soldier {platform}/{persona}")
        baseline = conn.execute(text("SELECT coalesce(max(event_id),0) FROM collection_events")).scalar_one()
    print(f"PREFLIGHT PASS database={EXPECTED_DB} revision={rev} "
          f"new_soldiers={len(COHORT)} max_attempts=2",flush=True)

    with engine.begin() as conn:
        ids = []
        for name, persona, platform in COHORT:
            soldier_id = conn.execute(text("""
                INSERT INTO soldiers (persona_id,platform,current_name,first_seen_at,last_seen_at)
                VALUES (:persona,:platform,:name,now(),now()) RETURNING soldier_id
            """), {"persona":persona,"platform":platform,"name":name}).scalar_one()
            ids.append(soldier_id)
            enqueue_job(conn, soldier_id=soldier_id, resource="detailed",
                        lane="background", priority_class="bootstrap",
                        reason="authorized_live_multiplatform_validation")
    identity = CollectorIdentity(
        collector_uuid=collector["collector_uuid"],collector_name=collector["collector_name"],
        hostname=collector["hostname"],egress_key=collector["egress_key"],lane="background",
    )
    results = []
    for index in range(len(ids)):
        result = collect_one_detailed_job(
            engine, identity=identity, request_interval_seconds=10.0,
            allowed_soldier_ids=ids, max_total_attempts=2,
            attempts_after_event_id=baseline, attempt_ceiling_resources=["detailed"],
            enforce_production_budget=True, lease_seconds=120, timeout_seconds=15.0,
            retry_after_seconds=3600,
        )
        print(f"COLLECT {index+1}: {result!r}",flush=True)
        results.append(result)
        if result is None or isinstance(result, FailedJob):
            break
    with engine.connect() as conn:
        for (name, persona, platform), soldier_id in zip(COHORT, ids):
            row = conn.execute(text("""
                SELECT cs.detailed_state,d.rank,d.kills,d.deaths,d.source_fetched_at
                FROM collection_state cs
                LEFT JOIN detailed_stats_current d USING(soldier_id)
                WHERE cs.soldier_id=:id
            """), {"id":soldier_id}).mappings().one_or_none()
            events = conn.execute(text("""
                SELECT event_type FROM collection_events WHERE soldier_id=:id
                AND resource='detailed' AND event_id>:baseline ORDER BY event_id
            """), {"id":soldier_id,"baseline":baseline}).scalars().all()
            history = conn.execute(text("""
                SELECT count(*) FROM detailed_stats_history WHERE soldier_id=:id
            """), {"id":soldier_id}).scalar_one()
            jobs = conn.execute(text("""
                SELECT count(*) FROM collection_jobs WHERE soldier_id=:id
            """), {"id":soldier_id}).scalar_one()
            print(f"VERIFY {platform} persona={persona} name={name!r} "
                  f"current={dict(row) if row else None} history={history} "
                  f"events={events} jobs={jobs}",flush=True)
            if len(results) == len(ids) and all(isinstance(r,CollectedJob) for r in results):
                assert row and row["detailed_state"] == "success"
                assert row["source_fetched_at"] is not None and history == 1 and jobs == 0
                assert events == ["collection_attempt_started","collection_success"]
    if len(results) != len(ids) or not all(isinstance(r,CollectedJob) for r in results):
        raise SystemExit("Cohort incomplete; inspect recorded state before retry")
    print("TWO-PLATFORM LIVE DETAILED COHORT PASS",flush=True)


if __name__ == "__main__":
    main()
