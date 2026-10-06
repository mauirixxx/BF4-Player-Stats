#!/usr/bin/env python3
"""Resume the interrupted Phase 5A ten-soldier weapon cohort.

This is intentionally tied to the preserved partial run: soldier 5 already
completed successfully; jobs 2212-2220 for soldiers 6-14 remain pristine.
At most nine additional Battlelog weapon attempts are permitted.
"""
from __future__ import annotations

from sqlalchemy import text

from bf4ps.db import make_engine
from bf4ps.weapon_collector import CollectorIdentity, collect_one_weapon_job

EXPECTED_DATABASE = "bf4_playerstats_test"
EXPECTED_REVISION = "0003_request_gates"
COLLECTOR_NAME = "phase3e-tcou"
HOSTNAME = "tcou"
REQUEST_INTERVAL_SECONDS = 5.0
SOLDIER_IDS = tuple(range(6, 15))
EXPECTED_JOB_IDS = tuple(range(2212, 2221))


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    suffix = f"  {detail}" if detail else ""
    print(f"{label:<70} {status}{suffix}")
    if not condition:
        raise AssertionError(f"{label}: {detail or 'condition was false'}")


def main() -> int:
    print("===== BF4PS PHASE 5A WEAPON COST COHORT RESUME =====")
    print("scope: preserved jobs 2212-2220 / at most 9 additional Battlelog weapon requests")
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

        jobs = conn.execute(text("""
            SELECT job_id, soldier_id, status, attempt_count, collector_uuid,
                   lease_token, started_at, lease_expires_at, reason
            FROM collection_jobs
            WHERE job_id BETWEEN 2212 AND 2220
            ORDER BY job_id
        """)).mappings().all()
        check("all nine preserved jobs still exist", len(jobs) == 9, str([dict(j) for j in jobs]))
        check("preserved job IDs are exact", tuple(int(j["job_id"]) for j in jobs) == EXPECTED_JOB_IDS)
        check("preserved soldier IDs are exact", tuple(int(j["soldier_id"]) for j in jobs) == SOLDIER_IDS)
        check("all preserved jobs are untouched pending work", all(
            j["status"] == "pending" and int(j["attempt_count"]) == 0
            and j["collector_uuid"] is None and j["lease_token"] is None
            and j["started_at"] is None and j["lease_expires_at"] is None
            and j["reason"] == "phase5a_weapon_cost_cohort"
            for j in jobs
        ))

        existing = int(conn.execute(text("""
            SELECT count(*) FROM collection_events
            WHERE resource='weapons'
              AND soldier_id BETWEEN 6 AND 14
              AND event_type IN ('collection_success','collection_failure')
        """)).scalar_one())
        check("resume cohort has no prior weapon attempt events", existing == 0, str(existing))

    identity = CollectorIdentity(
        collector_uuid=collector["collector_uuid"],
        collector_name=str(collector["collector_name"]),
        hostname=str(collector["hostname"]),
        egress_key=str(collector["egress_key"]),
        lane=str(collector["lane"]),
    )

    print("\n===== LIVE RESUME =====")
    for attempt in range(1, 10):
        result = collect_one_weapon_job(
            engine,
            identity=identity,
            request_interval_seconds=REQUEST_INTERVAL_SECONDS,
            allowed_soldier_ids=SOLDIER_IDS,
            max_total_attempts=9,
        )
        check(f"resume attempt {attempt:02d} produced one lifecycle result", result is not None, repr(result))
        print(f"resume attempt {attempt:02d}: {result!r}")

    with engine.connect() as conn:
        events = conn.execute(text("""
            SELECT event_id, soldier_id, persona_id, platform, result,
                   http_status, error_class, duration_ms, metadata
            FROM collection_events
            WHERE resource='weapons'
              AND soldier_id BETWEEN 6 AND 14
              AND event_type IN ('collection_success','collection_failure')
            ORDER BY event_id
        """)).mappings().all()

    check("exactly nine resume attempt events exist", len(events) == 9, str(len(events)))
    check("exactly one event exists for each resume soldier", {int(e["soldier_id"]) for e in events} == set(SOLDIER_IDS))

    print("\n===== RESUME EVIDENCE =====")
    for event in events:
        metadata = event["metadata"] or {}
        print(
            f"soldier={event['soldier_id']} persona={event['persona_id']} platform={event['platform']} "
            f"result={event['result']} http={event['http_status']} duration_ms={event['duration_ms']} "
            f"bytes={metadata.get('response_bytes', 0)} rows={metadata.get('weapon_rows', 0)} "
            f"error={event['error_class']}"
        )

    print("\nPHASE 5A WEAPON COST COHORT RESUME: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
