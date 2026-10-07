#!/usr/bin/env python3
"""Rollback-only Phase 5B Step 5 integrated scheduler lifecycle validation.

This harness performs no Battlelog requests. It requires one explicit existing
soldier in bf4_playerstats_test, exercises scheduler materialization inside a
single transaction, and always rolls that transaction back.
"""
from __future__ import annotations

import argparse
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import text

from bf4ps.db import make_engine
from bf4ps.background_service import claim_production_background_job
from bf4ps.collection_jobs import mark_job_running
from bf4ps.detailed_failure import DetailedFailure, persist_detailed_retry_failure
from bf4ps.detailed_persistence import DETAILED_FIELDS, persist_detailed_success
from bf4ps.retry_policy import retry_delay_for_failure
from bf4ps.production_scheduler import materialize_bf4sw_observation

EXPECTED_DATABASE = "bf4_playerstats_test"
EXPECTED_REVISION = "0003_request_gates"


def _assert_target(conn, soldier_id: int):
    database = conn.execute(text("SELECT current_database()")).scalar_one()
    if database != EXPECTED_DATABASE:
        raise RuntimeError(f"refusing database {database!r}; expected {EXPECTED_DATABASE!r}")

    revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    if revision != EXPECTED_REVISION:
        raise RuntimeError(f"refusing Alembic revision {revision!r}; expected {EXPECTED_REVISION!r}")

    row = conn.execute(
        text(
            """
            SELECT s.soldier_id, s.persona_id, s.platform, s.current_name,
                   ss.first_seen_at, ss.last_seen_at
            FROM soldiers AS s
            JOIN soldier_sources AS ss
              ON ss.soldier_id = s.soldier_id
             AND ss.source_type = 'bf4sw'
            JOIN collection_state AS cs
              ON cs.soldier_id = s.soldier_id
            WHERE s.soldier_id = :soldier_id
            FOR UPDATE OF s, ss, cs
            """
        ),
        {"soldier_id": soldier_id},
    ).mappings().one_or_none()
    if row is None:
        raise RuntimeError(
            f"soldier_id={soldier_id} must exist with bf4sw source and collection_state"
        )
    return row


def _clear_test_jobs(conn, soldier_id: int) -> None:
    owned = conn.execute(
        text(
            """
            SELECT COUNT(*)
            FROM collection_jobs
            WHERE soldier_id = :soldier_id
              AND status IN ('claimed', 'running')
            """
        ),
        {"soldier_id": soldier_id},
    ).scalar_one()
    if owned:
        raise RuntimeError(
            f"soldier_id={soldier_id} has {owned} claimed/running job(s); choose an idle soldier"
        )
    conn.execute(
        text("DELETE FROM collection_jobs WHERE soldier_id = :soldier_id"),
        {"soldier_id": soldier_id},
    )


def _jobs(conn, soldier_id: int):
    return conn.execute(
        text(
            """
            SELECT resource, lane, priority_class, reason, status, eligible_at
            FROM collection_jobs
            WHERE soldier_id = :soldier_id
            ORDER BY resource
            """
        ),
        {"soldier_id": soldier_id},
    ).mappings().all()


def _register_collector(conn):
    collector_uuid = uuid4()
    conn.execute(
        text(
            """
            INSERT INTO collectors
                (collector_uuid, collector_name, hostname, lane, egress_key,
                 enabled, drained, heartbeat_state)
            VALUES
                (:uuid, :name, 'phase5b-step5', 'background', :egress,
                 true, false, 'healthy')
            """
        ),
        {"uuid": collector_uuid, "name": f"phase5b-step5-{collector_uuid}",
         "egress": f"phase5b-step5-{collector_uuid}"},
    )
    return collector_uuid


def run_validation(soldier_id: int) -> None:
    engine = make_engine()
    conn = engine.connect()
    tx = conn.begin()
    try:
        soldier = _assert_target(conn, soldier_id)
        _clear_test_jobs(conn, soldier_id)
        collector_uuid = _register_collector(conn)

        as_of = conn.execute(text("SELECT clock_timestamp()")).scalar_one()
        observed_at = as_of - timedelta(minutes=5)

        # Scenario 1: a new soldier gets exactly one independent bootstrap job
        # for each retained-stat resource. Profile remains outside Phase 5B.
        conn.execute(
            text(
                """
                UPDATE soldier_sources
                SET last_seen_at = :observed_at
                WHERE soldier_id = :soldier_id AND source_type = 'bf4sw'
                """
            ),
            {"soldier_id": soldier_id, "observed_at": observed_at},
        )
        conn.execute(
            text(
                """
                UPDATE collection_state
                SET detailed_state = 'never_attempted', detailed_next_due_at = NULL,
                    weapons_state = 'never_attempted', weapons_next_due_at = NULL,
                    vehicles_state = 'never_attempted', vehicles_next_due_at = NULL
                WHERE soldier_id = :soldier_id
                """
            ),
            {"soldier_id": soldier_id},
        )
        result = materialize_bf4sw_observation(
            conn,
            soldier_id=soldier_id,
            observed_at=observed_at,
            as_of=as_of,
            newly_discovered=True,
        )
        jobs = _jobs(conn, soldier_id)
        assert result.source_class == "active"
        assert set(result.created_resources) == {"detailed", "weapons", "vehicles"}
        assert {row["resource"] for row in jobs} == {"detailed", "weapons", "vehicles"}
        assert all(row["priority_class"] == "bootstrap" for row in jobs)
        assert all(row["reason"] == "bf4sw_new_soldier" for row in jobs)

        # Replaying the same observation must be idempotent.
        replay = materialize_bf4sw_observation(
            conn,
            soldier_id=soldier_id,
            observed_at=observed_at,
            as_of=as_of,
            newly_discovered=True,
        )
        assert replay.created_resources == ()
        assert len(_jobs(conn, soldier_id)) == 3

        # Scenario 2: active returning soldier; only resources whose successful
        # due time has arrived materialize. Detailed and vehicles are due,
        # weapons is not.
        _clear_test_jobs(conn, soldier_id)
        conn.execute(
            text(
                """
                UPDATE collection_state
                SET detailed_state = 'success', detailed_next_due_at = :past_due,
                    weapons_state = 'success', weapons_next_due_at = :future_due,
                    vehicles_state = 'success', vehicles_next_due_at = :past_due
                WHERE soldier_id = :soldier_id
                """
            ),
            {
                "soldier_id": soldier_id,
                "past_due": observed_at - timedelta(seconds=1),
                "future_due": observed_at + timedelta(days=1),
            },
        )
        result = materialize_bf4sw_observation(
            conn,
            soldier_id=soldier_id,
            observed_at=observed_at,
            as_of=as_of,
            newly_discovered=False,
        )
        assert set(result.created_resources) == {"detailed", "vehicles"}
        jobs = _jobs(conn, soldier_id)
        assert {row["resource"] for row in jobs} == {"detailed", "vehicles"}
        assert all(row["priority_class"] == "active" for row in jobs)
        assert all(row["reason"] == "bf4sw_active_refresh" for row in jobs)

        # Scenario 3: the same due resources on a >24h source observation create
        # no refresh debt.
        _clear_test_jobs(conn, soldier_id)
        stale_observed_at = as_of - timedelta(days=2)
        conn.execute(
            text(
                """
                UPDATE soldier_sources
                SET last_seen_at = :observed_at
                WHERE soldier_id = :soldier_id AND source_type = 'bf4sw'
                """
            ),
            {"soldier_id": soldier_id, "observed_at": stale_observed_at},
        )
        conn.execute(
            text(
                """
                UPDATE collection_state
                SET detailed_next_due_at = :past_due,
                    weapons_next_due_at = :past_due,
                    vehicles_next_due_at = :past_due
                WHERE soldier_id = :soldier_id
                """
            ),
            {"soldier_id": soldier_id, "past_due": stale_observed_at - timedelta(days=1)},
        )
        result = materialize_bf4sw_observation(
            conn,
            soldier_id=soldier_id,
            observed_at=stale_observed_at,
            as_of=as_of,
            newly_discovered=False,
        )
        assert result.source_class == "recent"
        assert result.created_resources == ()
        assert _jobs(conn, soldier_id) == []

        print(
            "PASS: Phase 5B rollback-only DB validation "
            f"soldier_id={soldier['soldier_id']} persona_id={soldier['persona_id']} "
            f"platform={soldier['platform']} name={soldier['current_name']!r}"
        )
        print("  new bootstrap: detailed + weapons + vehicles exactly once")
        print("  active refresh: independently due resources only")
        print("  recent source observation: no new refresh debt")
        print("  Battlelog requests: 0")
        # Integrated lifecycle: rematerialize one active detailed job, admit it
        # through the production service, persist a retryable failure, prove
        # observation does not duplicate retry debt, then persist success.
        _clear_test_jobs(conn, soldier_id)
        active_observed = as_of - timedelta(minutes=1)
        conn.execute(text("""
            UPDATE soldier_sources SET last_seen_at = :observed_at
            WHERE soldier_id = :soldier_id AND source_type = 'bf4sw'
        """), {"soldier_id": soldier_id, "observed_at": active_observed})
        conn.execute(text("""
            UPDATE collection_state
            SET detailed_state='success', detailed_next_due_at=:past_due,
                detailed_consecutive_failures=0, detailed_last_error_class=NULL,
                weapons_state='success', weapons_next_due_at=:future_due,
                weapons_consecutive_failures=0,
                vehicles_state='success', vehicles_next_due_at=:future_due,
                vehicles_consecutive_failures=0
            WHERE soldier_id=:soldier_id
        """), {"soldier_id": soldier_id,
               "past_due": active_observed - timedelta(seconds=1),
               "future_due": active_observed + timedelta(days=3)})
        siblings = conn.execute(text("""
            SELECT weapons_state, weapons_next_due_at, weapons_consecutive_failures,
                   vehicles_state, vehicles_next_due_at, vehicles_consecutive_failures
            FROM collection_state WHERE soldier_id=:soldier_id
        """), {"soldier_id": soldier_id}).mappings().one()

        integrated = materialize_bf4sw_observation(
            conn, soldier_id=soldier_id, observed_at=active_observed,
            as_of=as_of, newly_discovered=False)
        assert integrated.created_resources == ("detailed",)
        job = claim_production_background_job(
            conn, collector_uuid=collector_uuid, resource="detailed")
        assert job is not None and mark_job_running(conn, job)

        retry_seconds = retry_delay_for_failure(
            conn, soldier_id=soldier_id, resource="detailed")
        assert retry_seconds == 900
        persist_detailed_retry_failure(
            conn, job=job,
            failure=DetailedFailure("phase5b_validation", "synthetic retryable failure"),
            attempted_at=as_of, persona_id=int(soldier["persona_id"]),
            platform=str(soldier["platform"]), collector_name="phase5b-step5",
            hostname="phase5b-step5", egress_key="phase5b-step5",
            duration_ms=0, retry_after_seconds=retry_seconds)

        retry_row = conn.execute(text("""
            SELECT job_id, eligible_at, last_error_at FROM collection_jobs
            WHERE soldier_id=:soldier_id AND resource='detailed'
        """), {"soldier_id": soldier_id}).mappings().one()
        state = conn.execute(text("""
            SELECT detailed_state, detailed_next_due_at, detailed_consecutive_failures
            FROM collection_state WHERE soldier_id=:soldier_id
        """), {"soldier_id": soldier_id}).mappings().one()
        assert state["detailed_state"] == "temporary_failure"
        assert state["detailed_consecutive_failures"] == 1
        assert state["detailed_next_due_at"] == as_of + timedelta(minutes=15)
        assert retry_row["eligible_at"] == as_of + timedelta(minutes=15)

        replay_observed = as_of + timedelta(minutes=5)
        conn.execute(text("""
            UPDATE soldier_sources SET last_seen_at=:observed_at
            WHERE soldier_id=:soldier_id AND source_type='bf4sw'
        """), {"soldier_id": soldier_id, "observed_at": replay_observed})
        replay = materialize_bf4sw_observation(
            conn, soldier_id=soldier_id, observed_at=replay_observed,
            as_of=replay_observed, newly_discovered=False)
        assert replay.created_resources == ()
        assert conn.execute(text("""
            SELECT COUNT(*) FROM collection_jobs
            WHERE soldier_id=:soldier_id AND resource='detailed'
        """), {"soldier_id": soldier_id}).scalar_one() == 1

        conn.execute(text("""
            UPDATE collection_jobs SET eligible_at=now()-interval '1 second'
            WHERE job_id=:job_id
        """), {"job_id": retry_row["job_id"]})
        retry_job = claim_production_background_job(
            conn, collector_uuid=collector_uuid, resource="detailed")
        assert retry_job is not None and retry_job.job_id == retry_row["job_id"]
        assert retry_job.attempt_count == 2 and mark_job_running(conn, retry_job)

        stats = {field: 0 for field in DETAILED_FIELDS}
        stats["quit_percentage"] = None
        stats["longest_headshot"] = None
        success_at = as_of + timedelta(minutes=16)
        persist_detailed_success(
            conn, job=retry_job, stats=stats, source_fetched_at=success_at,
            persona_id=int(soldier["persona_id"]), platform=str(soldier["platform"]),
            collector_name="phase5b-step5", hostname="phase5b-step5",
            egress_key="phase5b-step5", duration_ms=0)

        final_state = conn.execute(text("""
            SELECT detailed_state, detailed_last_success_at, detailed_next_due_at,
                   detailed_consecutive_failures, detailed_last_error_class,
                   weapons_state, weapons_next_due_at, weapons_consecutive_failures,
                   vehicles_state, vehicles_next_due_at, vehicles_consecutive_failures
            FROM collection_state WHERE soldier_id=:soldier_id
        """), {"soldier_id": soldier_id}).mappings().one()
        assert final_state["detailed_state"] == "success"
        assert final_state["detailed_consecutive_failures"] == 0
        assert final_state["detailed_last_error_class"] is None
        assert final_state["detailed_last_success_at"] == success_at
        assert final_state["detailed_next_due_at"] == success_at + timedelta(hours=24)
        for key in siblings:
            assert final_state[key] == siblings[key]
        assert conn.execute(text("""
            SELECT COUNT(*) FROM collection_jobs
            WHERE soldier_id=:soldier_id AND resource='detailed'
        """), {"soldier_id": soldier_id}).scalar_one() == 0

        print("  integrated failure/retry/success lifecycle: PASS")
        print("  retry backoff #1: 15 minutes")
        print("  pre-retry observation: no duplicate work")
        print("  retry claim: same job, attempt 2")
        print("  success reset: detailed due +24h")
        print("  weapons/vehicles state isolation: PASS")
        print("  committed database writes: 0 (transaction rolled back)")
    finally:
        if tx.is_active:
            tx.rollback()
        conn.close()
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rollback-only Phase 5B scheduler validation against one explicit test soldier."
    )
    parser.add_argument("--soldier-id", type=int, required=True)
    args = parser.parse_args()
    if args.soldier_id <= 0:
        parser.error("--soldier-id must be positive")
    run_validation(args.soldier_id)


if __name__ == "__main__":
    main()
