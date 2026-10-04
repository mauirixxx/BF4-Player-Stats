#!/usr/bin/env python3
"""Live test-database validation for Phase 2 collector registration/control."""

from __future__ import annotations

import os
from uuid import UUID

from sqlalchemy import create_engine, text

from bf4ps.collector_runtime import heartbeat_collector, register_collector, stop_collector
from bf4ps.detailed_collector import CollectorIdentity

COLLECTOR_UUID = UUID("5d69618d-0c16-4c5f-96e5-b5a18ea948c4")
IDENTITY = CollectorIdentity(
    collector_uuid=COLLECTOR_UUID,
    collector_name="phase2-drained-tcou",
    hostname="tcou",
    egress_key="phase2-drained-tcou",
    lane="background",
)


def main() -> None:
    engine = create_engine(os.environ["BF4PS_DATABASE_URL"])

    print("===== BF4PS PHASE 2 DRAINED RUNTIME INTEGRATION =====\n")

    with engine.begin() as conn:
        db = conn.execute(text("SELECT current_database()" )).scalar_one()
        recovery = conn.execute(text("SELECT pg_is_in_recovery()" )).scalar_one()
        if "test" not in db.lower():
            raise SystemExit(f"REFUSING: not a test database: {db}")
        if recovery:
            raise SystemExit("REFUSING: database is in recovery")

        # Harness owns only this fixed test identity. Remove a prior interrupted
        # harness row so the initial-registration behavior remains deterministic.
        conn.execute(
            text("DELETE FROM collectors WHERE collector_uuid = :uuid"),
            {"uuid": COLLECTOR_UUID},
        )

        before_jobs = conn.execute(text("SELECT COUNT(*) FROM collection_jobs")).scalar_one()
        before_events = conn.execute(text("SELECT COUNT(*) FROM collection_events")).scalar_one()

        initial = register_collector(conn, identity=IDENTITY, software_version="phase2-test")
        if not initial.may_claim:
            raise RuntimeError("new collector unexpectedly started non-runnable")

        conn.execute(
            text(
                "UPDATE collectors SET drained = true, updated_at = now() "
                "WHERE collector_uuid = :uuid"
            ),
            {"uuid": COLLECTOR_UUID},
        )

    print(f"database:       {db}")
    print(f"recovery:       {recovery}")
    print(f"collector_uuid: {COLLECTOR_UUID}")
    print(f"collector_name: {IDENTITY.collector_name}")
    print()

    with engine.begin() as conn:
        drained = heartbeat_collector(conn, collector_uuid=COLLECTOR_UUID)
        if drained.may_claim or not drained.drained or not drained.enabled:
            raise RuntimeError("drained control state not honored")

        first_heartbeat = conn.execute(
            text("SELECT last_heartbeat_at FROM collectors WHERE collector_uuid = :uuid"),
            {"uuid": COLLECTOR_UUID},
        ).scalar_one()

    with engine.begin() as conn:
        drained_again = heartbeat_collector(conn, collector_uuid=COLLECTOR_UUID)
        second_heartbeat = conn.execute(
            text("SELECT last_heartbeat_at FROM collectors WHERE collector_uuid = :uuid"),
            {"uuid": COLLECTOR_UUID},
        ).scalar_one()
        if drained_again.may_claim:
            raise RuntimeError("second heartbeat lost drained control")

    # Simulate a normal process restart using the exact same configured UUID.
    with engine.begin() as conn:
        restarted = register_collector(conn, identity=IDENTITY, software_version="phase2-test")
        if restarted.may_claim or not restarted.drained or not restarted.enabled:
            raise RuntimeError("restart overwrote operator drained state")

        row = conn.execute(
            text(
                """
                SELECT collector_name, hostname, lane, egress_key, enabled, drained,
                       heartbeat_state, last_heartbeat_at
                FROM collectors
                WHERE collector_uuid = :uuid
                """
            ),
            {"uuid": COLLECTOR_UUID},
        ).mappings().one()

        after_jobs = conn.execute(text("SELECT COUNT(*) FROM collection_jobs")).scalar_one()
        after_events = conn.execute(text("SELECT COUNT(*) FROM collection_events")).scalar_one()

    print("===== CONTROL / HEARTBEAT VALIDATION =====")
    print(f"registered stable identity: PASS")
    print(f"drained blocks claims:      PASS")
    print(f"heartbeat 1:                {first_heartbeat}")
    print(f"heartbeat 2:                {second_heartbeat}")
    print(f"heartbeat remains healthy:  {'PASS' if row['heartbeat_state'] == 'healthy' else 'FAIL'}")
    print(f"restart preserves UUID:     PASS")
    print(f"restart preserves drained:  PASS")
    print(f"queue rows unchanged:       {'PASS' if after_jobs == before_jobs else 'FAIL'}")
    print(f"events unchanged:           {'PASS' if after_events == before_events else 'FAIL'}")

    if row["heartbeat_state"] != "healthy":
        raise RuntimeError("collector heartbeat is not healthy")
    if after_jobs != before_jobs:
        raise RuntimeError("drained runtime harness changed collection queue")
    if after_events != before_events:
        raise RuntimeError("routine heartbeat/registration created collection events")

    with engine.begin() as conn:
        if not stop_collector(conn, collector_uuid=COLLECTOR_UUID):
            raise RuntimeError("clean stop marker failed")
        stopped = conn.execute(
            text(
                "SELECT heartbeat_state, enabled, drained FROM collectors "
                "WHERE collector_uuid = :uuid"
            ),
            {"uuid": COLLECTOR_UUID},
        ).mappings().one()

    print(f"clean stop state:           {'PASS' if stopped['heartbeat_state'] == 'unknown' else 'FAIL'}")
    print(f"controls survive stop:      {'PASS' if stopped['enabled'] and stopped['drained'] else 'FAIL'}")

    if stopped["heartbeat_state"] != "unknown" or not stopped["enabled"] or not stopped["drained"]:
        raise RuntimeError("clean stop corrupted collector state/control")

    # Leave the deliberately drained test collector registered for inspection.
    print("\nDrained test collector row intentionally retained for inspection.")
    print("No feeder pass, job claim, or Battlelog request was performed.")
    print("\nBF4PS PHASE 2 DRAINED RUNTIME INTEGRATION: PASS")


if __name__ == "__main__":
    main()
