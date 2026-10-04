"""Live end-to-end validation of one BF4PS detailed-statistics collection."""

from __future__ import annotations

import os
from uuid import uuid4

from sqlalchemy import create_engine, text

from bf4ps.collection_jobs import enqueue_job
from bf4ps.detailed_collector import CollectorIdentity, collect_one_detailed_job

PERSONA_ID = 236753552
PLATFORM = "pc"
COLLECTOR_NAME = "phase1-patient-zero"
HOSTNAME = "tcou"
EGRESS_KEY = "phase1-patient-zero-tcou"
REASON = "phase1_patient_zero"


def main() -> None:
    database_url = os.environ.get("BF4PS_DATABASE_URL")
    if not database_url:
        raise SystemExit("BF4PS_DATABASE_URL is required")

    engine = create_engine(database_url)
    collector_uuid = uuid4()

    print("===== BF4PS PHASE 1 PATIENT ZERO =====")
    print()

    with engine.begin() as conn:
        database_name = conn.execute(text("SELECT current_database()" )).scalar_one()
        recovery = conn.execute(text("SELECT pg_is_in_recovery()" )).scalar_one()

        if "test" not in database_name.lower():
            raise SystemExit(f"REFUSING TO RUN against non-test database: {database_name}")
        if recovery:
            raise SystemExit("REFUSING TO RUN against a PostgreSQL recovery node")

        soldier = conn.execute(
            text(
                """
                SELECT soldier_id, persona_id, platform, current_name
                FROM soldiers
                WHERE persona_id = :persona_id
                  AND platform = :platform
                """
            ),
            {"persona_id": PERSONA_ID, "platform": PLATFORM},
        ).mappings().one_or_none()
        if soldier is None:
            raise SystemExit("Patient Zero soldier is not present in BF4PS test database")

        soldier_id = int(soldier["soldier_id"])

        existing = conn.execute(
            text(
                """
                SELECT job_id, status, reason
                FROM collection_jobs
                WHERE soldier_id = :soldier_id
                  AND resource = 'detailed'
                """
            ),
            {"soldier_id": soldier_id},
        ).mappings().one_or_none()
        if existing is not None:
            raise SystemExit(
                "REFUSING TO RUN: Patient Zero already has detailed work: "
                f"job={existing['job_id']} status={existing['status']} reason={existing['reason']}"
            )

        conn.execute(
            text(
                """
                INSERT INTO collectors (
                    collector_uuid, collector_name, hostname, lane, egress_key,
                    enabled, drained, heartbeat_state
                ) VALUES (
                    :collector_uuid, :collector_name, :hostname, 'background',
                    :egress_key, true, false, 'healthy'
                )
                """
            ),
            {
                "collector_uuid": collector_uuid,
                "collector_name": COLLECTOR_NAME,
                "hostname": HOSTNAME,
                "egress_key": EGRESS_KEY,
            },
        )

        job_id = enqueue_job(
            conn,
            soldier_id=soldier_id,
            resource="detailed",
            lane="background",
            priority_class="interactive",
            reason=REASON,
            priority_value=1000,
        )

    print(f"database:       {database_name}")
    print(f"recovery:       {recovery}")
    print(f"soldier:        {soldier['current_name']} ({PERSONA_ID}, {PLATFORM})")
    print(f"soldier_id:     {soldier_id}")
    print(f"job_id:         {job_id}")
    print(f"collector_uuid: {collector_uuid}")
    print(f"egress_key:     {EGRESS_KEY}")
    print()
    print("Issuing exactly one end-to-end collector invocation...")

    identity = CollectorIdentity(
        collector_uuid=collector_uuid,
        collector_name=COLLECTOR_NAME,
        hostname=HOSTNAME,
        egress_key=EGRESS_KEY,
    )

    result = collect_one_detailed_job(
        engine,
        identity=identity,
        request_interval_seconds=2.0,
        lease_seconds=120,
        timeout_seconds=15.0,
    )
    if result is None:
        raise AssertionError("Patient Zero job was not claimed")
    if result.job_id != job_id:
        raise AssertionError(f"unexpected job collected: expected {job_id}, got {result.job_id}")

    with engine.begin() as conn:
        current = conn.execute(
            text(
                """
                SELECT *
                FROM detailed_stats_current
                WHERE soldier_id = :soldier_id
                """
            ),
            {"soldier_id": soldier_id},
        ).mappings().one_or_none()

        history_count = conn.execute(
            text("SELECT COUNT(*) FROM detailed_stats_history WHERE soldier_id = :soldier_id"),
            {"soldier_id": soldier_id},
        ).scalar_one()

        state = conn.execute(
            text(
                """
                SELECT detailed_state, detailed_last_attempt_at,
                       detailed_last_success_at, detailed_consecutive_failures,
                       detailed_last_error_class, detailed_last_error_message
                FROM collection_state
                WHERE soldier_id = :soldier_id
                """
            ),
            {"soldier_id": soldier_id},
        ).mappings().one_or_none()

        event = conn.execute(
            text(
                """
                SELECT event_id, event_type, result, attempt_number,
                       duration_ms, http_status, collector_uuid,
                       collector_name_snapshot, hostname_snapshot,
                       egress_key_snapshot, metadata
                FROM collection_events
                WHERE job_id = :job_id
                ORDER BY event_id DESC
                LIMIT 1
                """
            ),
            {"job_id": job_id},
        ).mappings().one_or_none()

        remaining_job = conn.execute(
            text("SELECT COUNT(*) FROM collection_jobs WHERE job_id = :job_id"),
            {"job_id": job_id},
        ).scalar_one()

        if current is None:
            raise AssertionError("detailed_stats_current row was not written")
        if history_count < 1:
            raise AssertionError("detailed_stats_history row was not written")
        if state is None or state["detailed_state"] != "success":
            raise AssertionError("collection_state was not marked successful")
        if event is None or event["event_type"] != "collection_success" or event["result"] != "success":
            raise AssertionError("collection_success event was not written")
        if remaining_job != 0:
            raise AssertionError("completed Patient Zero queue job still exists")

        # Preserve Patient Zero stats/history/state/event. Only remove ephemeral
        # coordination records created specifically by this harness.
        gate_deleted = conn.execute(
            text("DELETE FROM request_gates WHERE egress_key = :egress_key"),
            {"egress_key": EGRESS_KEY},
        ).rowcount
        collector_deleted = conn.execute(
            text("DELETE FROM collectors WHERE collector_uuid = :collector_uuid"),
            {"collector_uuid": collector_uuid},
        ).rowcount

    print()
    print("===== COLLECTION RESULT =====")
    print(f"history appended: {result.history_appended}")
    print(f"duration_ms:      {result.duration_ms}")
    print(f"source fetched:   {current['source_fetched_at']}")
    print(f"rank:             {current['rank']}")
    print(f"time played:      {current['time_played_seconds']}")
    print(f"total score:      {current['total_score']}")
    print(f"kills:            {current['kills']}")
    print(f"deaths:           {current['deaths']}")
    print()
    print("===== DATABASE VALIDATION =====")
    print(f"current row:       PASS")
    print(f"history rows:      {history_count}")
    print(f"collection state:  {state['detailed_state']}")
    print(f"success event:     PASS (event_id={event['event_id']}, http={event['http_status']})")
    print(f"queue finalized:   PASS")
    print(f"gate cleanup:      {gate_deleted}")
    print(f"collector cleanup: {collector_deleted}")
    print()
    print("Patient Zero statistics/history/state/event were intentionally retained.")
    print()
    print("BF4PS PHASE 1 PATIENT ZERO: PASS")


if __name__ == "__main__":
    main()
