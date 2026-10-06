#!/usr/bin/env python3
"""One-request live Phase 5A weapon collector probe against the test database."""
from __future__ import annotations

from sqlalchemy import text

from bf4ps.collection_jobs import enqueue_job
from bf4ps.db import make_engine
from bf4ps.weapon_collector import CollectorIdentity, collect_one_weapon_job

EXPECTED_DATABASE = "bf4_playerstats_test"
EXPECTED_REVISION = "0003_request_gates"
COLLECTOR_NAME = "phase3e-tcou"
HOSTNAME = "tcou"
REQUEST_INTERVAL_SECONDS = 5.0


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    suffix = f"  {detail}" if detail else ""
    print(f"{label:<70} {status}{suffix}")
    if not condition:
        raise AssertionError(f"{label}: {detail or 'condition was false'}")


def main() -> int:
    print("===== BF4PS PHASE 5A SINGLE LIVE WEAPON PROBE =====")
    print("scope: exactly one eligible soldier / at most one Battlelog weapon request")
    engine = make_engine()

    with engine.connect() as conn:
        db = conn.execute(text("SELECT current_database()" )).scalar_one()
        revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        recovery = bool(conn.execute(text("SELECT pg_is_in_recovery()" )).scalar_one())
        read_only = conn.execute(text("SELECT current_setting('transaction_read_only')" )).scalar_one()
        check("target database is bf4_playerstats_test", db == EXPECTED_DATABASE, str(db))
        check("target is writable primary", not recovery and read_only == "off", f"recovery={recovery} read_only={read_only}")
        check("Alembic revision is frozen Phase 5A revision", revision == EXPECTED_REVISION, str(revision))

        collector = conn.execute(text("""
            SELECT collector_uuid, collector_name, hostname, egress_key, lane,
                   enabled, drained, current_job_id, retired_at
            FROM collectors
            WHERE collector_name=:collector_name AND retired_at IS NULL
        """), {"collector_name": COLLECTOR_NAME}).mappings().one()
        check("tcou collector identity is exact", collector["hostname"] == HOSTNAME, str(dict(collector)))
        check("tcou collector is enabled and undrained", bool(collector["enabled"]) and not bool(collector["drained"]))
        check("tcou collector is idle", collector["current_job_id"] is None)

        candidate = conn.execute(text("""
            SELECT s.soldier_id, s.persona_id, s.current_name, s.platform
            FROM soldiers s
            JOIN collection_state cs ON cs.soldier_id=s.soldier_id
            WHERE cs.detailed_state='success'
              AND cs.weapons_state='never_attempted'
              AND NOT EXISTS (SELECT 1 FROM soldier_weapon_stats sw WHERE sw.soldier_id=s.soldier_id)
              AND NOT EXISTS (SELECT 1 FROM collection_jobs j WHERE j.soldier_id=s.soldier_id AND j.resource='weapons')
              AND NOT EXISTS (SELECT 1 FROM collection_events e WHERE e.soldier_id=s.soldier_id AND e.resource='weapons')
            ORDER BY s.soldier_id
            LIMIT 1
        """)).mappings().one_or_none()
        check("one pristine weapon candidate exists", candidate is not None)
        assert candidate is not None
        soldier_id = int(candidate["soldier_id"])
        print(f"candidate: soldier={soldier_id} persona={candidate['persona_id']} name={candidate['current_name']!r} platform={candidate['platform']}")

    with engine.begin() as conn:
        job_id = enqueue_job(conn, soldier_id=soldier_id, resource="weapons", lane="background",
                             priority_class="bootstrap", reason="phase5a_single_live_probe", priority_value=1000000)
    print(f"queued weapon job: {job_id}")

    identity = CollectorIdentity(
        collector_uuid=collector["collector_uuid"], collector_name=str(collector["collector_name"]),
        hostname=str(collector["hostname"]), egress_key=str(collector["egress_key"]),
        lane=str(collector["lane"]),
    )
    result = collect_one_weapon_job(
        engine, identity=identity, request_interval_seconds=REQUEST_INTERVAL_SECONDS,
        allowed_soldier_ids=[soldier_id], max_total_attempts=1,
    )
    check("collector produced one lifecycle result", result is not None, repr(result))
    print(f"result: {result!r}")

    with engine.connect() as conn:
        state = conn.execute(text("""
            SELECT weapons_state, weapons_consecutive_failures,
                   weapons_last_error_class, weapons_last_error_message
            FROM collection_state WHERE soldier_id=:soldier_id
        """), {"soldier_id": soldier_id}).mappings().one()
        events = conn.execute(text("""
            SELECT event_id, event_type, result, http_status, error_class,
                   duration_ms, metadata
            FROM collection_events
            WHERE soldier_id=:soldier_id AND resource='weapons'
            ORDER BY event_id
        """), {"soldier_id": soldier_id}).mappings().all()
        rows = int(conn.execute(text("SELECT count(*) FROM soldier_weapon_stats WHERE soldier_id=:soldier_id"), {"soldier_id": soldier_id}).scalar_one())
        job = conn.execute(text("""
            SELECT job_id, status, attempt_count, collector_uuid, lease_token,
                   eligible_at, last_error_class
            FROM collection_jobs WHERE soldier_id=:soldier_id AND resource='weapons'
        """), {"soldier_id": soldier_id}).mappings().one_or_none()

    check("exactly one weapon attempt event exists", len(events) == 1, str([dict(e) for e in events]))
    event = events[0]
    check("attempt event is lifecycle-valid", event["event_type"] in ("collection_success", "collection_failure"), str(dict(event)))
    if event["result"] == "success":
        check("weapon state converged to success", state["weapons_state"] == "success", str(dict(state)))
        check("successful payload persisted weapon rows", rows > 0, str(rows))
        check("successful job finalized", job is None, str(dict(job)) if job else "deleted")
        metadata = event["metadata"] or {}
        check("measured response bytes recorded", int(metadata.get("response_bytes", 0)) > 0, str(metadata))
        check("persisted row count matches event metadata", rows == int(metadata.get("weapon_rows", -1)), f"rows={rows} metadata={metadata}")
    else:
        check("failure is retryable state", state["weapons_state"] == "temporary_failure", str(dict(state)))
        check("failed payload persisted no weapon rows", rows == 0, str(rows))
        check("retry job is pending and unowned", job is not None and job["status"] == "pending" and job["collector_uuid"] is None and job["lease_token"] is None, str(dict(job)) if job else "missing")

    print("\n===== ACCEPTANCE =====")
    print("Battlelog weapon requests: 1")
    print(f"lifecycle result: {event['result']}")
    print(f"weapon rows: {rows}")
    print(f"event: {dict(event)}")
    print("PHASE 5A SINGLE LIVE WEAPON PROBE: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
