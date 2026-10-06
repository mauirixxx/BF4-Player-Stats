#!/usr/bin/env python3
"""Rollback-only Phase 5B production-scheduler database validation.

This harness performs no Battlelog requests. It requires one explicit existing
soldier in bf4_playerstats_test, exercises scheduler materialization inside a
single transaction, and always rolls that transaction back.
"""
from __future__ import annotations

import argparse
from datetime import timedelta

from sqlalchemy import text

from bf4ps.db import make_engine
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


def run_validation(soldier_id: int) -> None:
    engine = make_engine()
    conn = engine.connect()
    tx = conn.begin()
    try:
        soldier = _assert_target(conn, soldier_id)
        _clear_test_jobs(conn, soldier_id)

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
