#!/usr/bin/env python3
"""Deterministic Phase 3C drain/stop/restart operator lifecycle proof.

This database-mutating integration harness exercises the real collector registry,
heartbeat/control, queue-claim, stop, and fenced finalization primitives. It
performs no Battlelog requests and cleans up only its frozen test rows.
"""

from __future__ import annotations

import os
from uuid import UUID

from sqlalchemy import create_engine, text

from bf4ps.collection_jobs import claim_next_job, finalize_owned_job, mark_job_running
from bf4ps.collector_runtime import heartbeat_collector, register_collector, stop_collector
from bf4ps.detailed_collector import CollectorIdentity

EXPECTED_ALEMBIC = "0003_request_gates"
DATABASE_NAME_FRAGMENT = "test"
RESOURCE = "detailed"
LANE = "background"
TEST_SOLDIERS = (25, 26, 27)
LEASE_SECONDS = 30
REASON = "phase3c_operator_lifecycle_proof"

COLLECTOR_A = UUID("b2b3ef60-62e8-4d4a-91b0-41a2e2a3c001")
COLLECTOR_B = UUID("b2b3ef60-62e8-4d4a-91b0-41a2e2a3c002")
EGRESS_KEY = "phase3c-lifecycle-tcou"

IDENTITY_A = CollectorIdentity(COLLECTOR_A, "phase3c-tcou-a", "tcou", EGRESS_KEY, LANE)
IDENTITY_B = CollectorIdentity(COLLECTOR_B, "phase3c-tcou-b", "tcou", EGRESS_KEY, LANE)


def _claim_if_allowed(engine, identity: CollectorIdentity):
    with engine.begin() as conn:
        control = heartbeat_collector(conn, collector_uuid=identity.collector_uuid)
        if not control.may_claim:
            return control, None
        claim = claim_next_job(
            conn,
            collector_uuid=identity.collector_uuid,
            lane=identity.lane,
            resource=RESOURCE,
            lease_seconds=LEASE_SECONDS,
        )
        return control, claim


def _collector_row(engine, collector_uuid: UUID):
    with engine.connect() as conn:
        return conn.execute(
            text(
                """
                SELECT collector_uuid, collector_name, hostname, lane, egress_key,
                       enabled, drained, started_at, heartbeat_state, current_job_id,
                       retired_at
                FROM collectors
                WHERE collector_uuid = :collector_uuid
                """
            ),
            {"collector_uuid": collector_uuid},
        ).mappings().one_or_none()


def _set_drained(engine, collector_uuid: UUID, drained: bool) -> None:
    with engine.begin() as conn:
        changed = conn.execute(
            text(
                """
                UPDATE collectors
                SET drained = :drained, updated_at = now()
                WHERE collector_uuid = :collector_uuid
                  AND retired_at IS NULL
                """
            ),
            {"collector_uuid": collector_uuid, "drained": drained},
        ).rowcount
        if changed != 1:
            raise RuntimeError(f"failed to set drained={drained} for {collector_uuid}")


def main() -> None:
    engine = create_engine(os.environ["BF4PS_DATABASE_URL"])

    with engine.connect() as conn:
        db = str(conn.execute(text("SELECT current_database()")).scalar_one())
        recovery = bool(conn.execute(text("SELECT pg_is_in_recovery()")).scalar_one())
        alembic = str(conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one())
        existing_queue = int(conn.execute(text("SELECT COUNT(*) FROM collection_jobs WHERE resource=:resource AND lane=:lane"), {"resource": RESOURCE, "lane": LANE}).scalar_one())
        collector_conflicts = int(conn.execute(text("SELECT COUNT(*) FROM collectors WHERE collector_uuid = ANY(:ids) OR lower(collector_name) IN (lower('phase3c-tcou-a'), lower('phase3c-tcou-b'))"), {"ids": [COLLECTOR_A, COLLECTOR_B]}).scalar_one())
        soldiers = conn.execute(
            text(
                """
                SELECT s.soldier_id, s.platform, s.current_name, cs.detailed_state
                FROM soldiers AS s
                JOIN collection_state AS cs ON cs.soldier_id = s.soldier_id
                WHERE s.soldier_id = ANY(:ids)
                ORDER BY s.soldier_id
                """
            ),
            {"ids": list(TEST_SOLDIERS)},
        ).mappings().all()

    print("===== BF4PS PHASE 3C OPERATOR LIFECYCLE PROOF =====")
    print()
    print("DATABASE-MUTATING INTEGRATION HARNESS")
    print("Exact test rows are cleaned up. No Battlelog request is performed.")
    print()
    print(f"database:        {db}")
    print(f"recovery:        {recovery}")
    print(f"alembic:         {alembic}")
    print(f"resource/lane:   {RESOURCE}/{LANE}")
    print(f"test soldiers:   {list(TEST_SOLDIERS)}")
    print(f"collector A:     {COLLECTOR_A}")
    print(f"collector B:     {COLLECTOR_B}")
    print()

    if DATABASE_NAME_FRAGMENT not in db.lower():
        raise SystemExit(f"REFUSING: not a test database: {db}")
    if recovery:
        raise SystemExit("REFUSING: database is in recovery")
    if alembic != EXPECTED_ALEMBIC:
        raise SystemExit(f"REFUSING: expected Alembic {EXPECTED_ALEMBIC}, got {alembic}")
    if existing_queue != 0:
        raise SystemExit(f"REFUSING: expected empty detailed/background queue, found {existing_queue}")
    if collector_conflicts:
        raise SystemExit(f"REFUSING: deterministic collector identities already exist ({collector_conflicts})")
    if [int(row["soldier_id"]) for row in soldiers] != list(TEST_SOLDIERS):
        raise SystemExit("REFUSING: frozen Phase 3C soldiers are not present exactly")
    if any(str(row["detailed_state"]) != "never_attempted" for row in soldiers):
        raise SystemExit("REFUSING: frozen Phase 3C soldiers are not pristine")

    try:
        with engine.begin() as conn:
            control_a = register_collector(conn, identity=IDENTITY_A, software_version="phase3c-proof")
            control_b = register_collector(conn, identity=IDENTITY_B, software_version="phase3c-proof")
            for soldier_id in TEST_SOLDIERS:
                conn.execute(
                    text(
                        """
                        INSERT INTO collection_jobs (
                            soldier_id, resource, lane, priority_class, reason,
                            status, priority_value, eligible_at
                        ) VALUES (
                            :soldier_id, :resource, :lane, 'bootstrap', :reason,
                            'pending', 0, now()
                        )
                        """
                    ),
                    {"soldier_id": soldier_id, "resource": RESOURCE, "lane": LANE, "reason": REASON},
                )

        # A owns one job before the operator requests drain. Drain must prevent
        # new claims, not silently abandon already-owned work.
        _, claim_a = _claim_if_allowed(engine, IDENTITY_A)
        if claim_a is None:
            raise RuntimeError("collector A failed to obtain initial work")
        with engine.begin() as conn:
            if not mark_job_running(conn, claim_a):
                raise RuntimeError("collector A could not mark initial job running")

        _set_drained(engine, COLLECTOR_A, True)
        drained_control, blocked_claim = _claim_if_allowed(engine, IDENTITY_A)

        # Existing owned work completes gracefully under the ownership token.
        with engine.begin() as conn:
            a_finalized = finalize_owned_job(conn, claim_a)

        # B continues consuming while A is drained.
        _, claim_b = _claim_if_allowed(engine, IDENTITY_B)
        if claim_b is None:
            raise RuntimeError("collector B did not continue while A was drained")
        with engine.begin() as conn:
            b_running = mark_job_running(conn, claim_b)
            b_finalized = finalize_owned_job(conn, claim_b) if b_running else False

        row_a_before_stop = _collector_row(engine, COLLECTOR_A)
        with engine.begin() as conn:
            stopped_a = stop_collector(conn, collector_uuid=COLLECTOR_A)
        row_a_stopped = _collector_row(engine, COLLECTOR_A)

        # Restart under the same UUID/configuration. Registration must preserve
        # operator-owned drained state.
        with engine.begin() as conn:
            restart_control = register_collector(conn, identity=IDENTITY_A, software_version="phase3c-proof-restart")
        row_a_restarted = _collector_row(engine, COLLECTOR_A)
        restart_blocked_control, restart_claim = _claim_if_allowed(engine, IDENTITY_A)

        # Only an explicit operator undrain permits A to compete again.
        _set_drained(engine, COLLECTOR_A, False)
        resumed_control, resumed_claim = _claim_if_allowed(engine, IDENTITY_A)
        if resumed_claim is None:
            raise RuntimeError("collector A failed to rejoin after explicit undrain")
        with engine.begin() as conn:
            resumed_running = mark_job_running(conn, resumed_claim)
            resumed_finalized = finalize_owned_job(conn, resumed_claim) if resumed_running else False

        row_a_final = _collector_row(engine, COLLECTOR_A)
        row_b_final = _collector_row(engine, COLLECTOR_B)
        with engine.connect() as conn:
            remaining_jobs = int(conn.execute(text("SELECT COUNT(*) FROM collection_jobs WHERE reason=:reason"), {"reason": REASON}).scalar_one())

        identity_preserved = (
            row_a_before_stop is not None and row_a_restarted is not None
            and row_a_before_stop["collector_uuid"] == row_a_restarted["collector_uuid"] == COLLECTOR_A
            and row_a_before_stop["collector_name"] == row_a_restarted["collector_name"] == IDENTITY_A.collector_name
            and row_a_before_stop["hostname"] == row_a_restarted["hostname"] == IDENTITY_A.hostname
            and row_a_before_stop["lane"] == row_a_restarted["lane"] == IDENTITY_A.lane
            and row_a_before_stop["egress_key"] == row_a_restarted["egress_key"] == IDENTITY_A.egress_key
        )
        controls_preserved = bool(
            restart_control.enabled and restart_control.drained
            and restart_blocked_control.enabled and restart_blocked_control.drained
            and row_a_restarted is not None and row_a_restarted["drained"] is True
        )

        checks = {
            "initial collectors enabled/undrained": control_a.may_claim and control_b.may_claim,
            "A drain visible through heartbeat": drained_control.enabled and drained_control.drained,
            "drained A accepts no new work": blocked_claim is None,
            "A gracefully finalizes owned work": a_finalized,
            "B continues while A drained": b_running and b_finalized,
            "A clean stop succeeds": stopped_a and row_a_stopped is not None and row_a_stopped["heartbeat_state"] == "unknown",
            "restart preserves same identity": identity_preserved,
            "restart preserves drained control": controls_preserved,
            "restarted drained A still blocked": restart_claim is None,
            "explicit undrain enables A": resumed_control.may_claim,
            "A safely rejoins and finalizes": resumed_running and resumed_finalized,
            "all frozen jobs finalized": remaining_jobs == 0,
            "collector rows remain distinct": row_a_final is not None and row_b_final is not None and row_a_final["collector_uuid"] != row_b_final["collector_uuid"],
        }

        print("===== LIFECYCLE OBSERVATIONS =====")
        print(f"A initial job:             soldier={claim_a.soldier_id} attempt={claim_a.attempt_count}")
        print(f"A drained/new claim:       {'BLOCKED' if blocked_claim is None else 'UNEXPECTED CLAIM'}")
        print(f"B continued with soldier:  {claim_b.soldier_id}")
        print(f"A stopped heartbeat:       {row_a_stopped['heartbeat_state'] if row_a_stopped else None}")
        print(f"A restart control:         enabled={restart_control.enabled} drained={restart_control.drained}")
        print(f"A restart/new claim:       {'BLOCKED' if restart_claim is None else 'UNEXPECTED CLAIM'}")
        print(f"A explicit undrain:        enabled={resumed_control.enabled} drained={resumed_control.drained}")
        print(f"A resumed with soldier:    {resumed_claim.soldier_id}")
        print()
        print("===== FINAL VALIDATION =====")
        for label, passed in checks.items():
            print(f"{label:<40} {'PASS' if passed else 'FAIL'}")
        print("Battlelog requests:                       0")
        if not all(checks.values()):
            raise RuntimeError("Phase 3C operator lifecycle validation failed")

    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM collection_jobs WHERE reason=:reason"), {"reason": REASON})
            conn.execute(text("DELETE FROM collectors WHERE collector_uuid = ANY(:ids)"), {"ids": [COLLECTOR_A, COLLECTOR_B]})
        with engine.connect() as conn:
            jobs_left = int(conn.execute(text("SELECT COUNT(*) FROM collection_jobs WHERE reason=:reason"), {"reason": REASON}).scalar_one())
            collectors_left = int(conn.execute(text("SELECT COUNT(*) FROM collectors WHERE collector_uuid = ANY(:ids)"), {"ids": [COLLECTOR_A, COLLECTOR_B]}).scalar_one())
        cleanup_ok = jobs_left == 0 and collectors_left == 0
        print(f"exact cleanup:                            {'PASS' if cleanup_ok else 'FAIL'}")
        if not cleanup_ok:
            raise RuntimeError(f"cleanup failed: jobs={jobs_left} collectors={collectors_left}")

    print()
    print("BF4PS PHASE 3C OPERATOR LIFECYCLE PROOF: PASS")


if __name__ == "__main__":
    main()
