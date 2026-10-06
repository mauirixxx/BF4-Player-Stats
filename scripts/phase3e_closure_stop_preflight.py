#!/usr/bin/env python3
"""Read-only preflight for the final Phase 3E clean-stop closure."""
from __future__ import annotations

import os

from sqlalchemy import create_engine, text, bindparam

from phase3e_lifecycle_a_common import FROZEN_UUIDS, HOSTS, assert_target

CLOSURE_JOBS = (814, 815, 816)
CLOSURE_SOLDIERS = (390, 391, 392)


def main() -> int:
    url = os.environ.get("BF4PS_DATABASE_URL")
    if not url:
        raise SystemExit("REFUSING: BF4PS_DATABASE_URL is not set")

    engine = create_engine(url, pool_pre_ping=True)
    with engine.connect() as conn:
        assert_target(conn)
        collectors = conn.execute(
            text("""
                SELECT collector_uuid,collector_name,hostname,lane,egress_key,
                       enabled,drained,software_version,started_at,last_heartbeat_at,
                       heartbeat_state,heartbeat_lost_at,current_job_id,retired_at
                FROM collectors
                WHERE collector_uuid IN :uuids
                ORDER BY hostname
            """).bindparams(bindparam("uuids", expanding=True)),
            {"uuids": list(FROZEN_UUIDS)},
        ).mappings().all()
        jobs = conn.execute(
            text("""
                SELECT job_id,soldier_id,status,attempt_count,collector_uuid,lease_token
                FROM collection_jobs
                WHERE job_id IN :jobs OR soldier_id IN :soldiers
                ORDER BY job_id
            """).bindparams(
                bindparam("jobs", expanding=True),
                bindparam("soldiers", expanding=True),
            ),
            {"jobs": list(CLOSURE_JOBS), "soldiers": list(CLOSURE_SOLDIERS)},
        ).mappings().all()
        events = conn.execute(text("""
            SELECT event_id,job_id,soldier_id,event_type,attempt_number,result,http_status,
                   collector_uuid,collector_name_snapshot,hostname_snapshot,lease_token
            FROM collection_events
            WHERE event_id BETWEEN 812 AND 814
            ORDER BY event_id
        """)).mappings().all()

    print("===== BF4PS PHASE 3E CLEAN-STOP PREFLIGHT =====")
    cmap = {row["collector_uuid"]: row for row in collectors}
    identities_ok = len(cmap) == 3
    for hostname, frozen in HOSTS.items():
        row = cmap.get(frozen.collector_uuid)
        exact = row is not None and (
            row["collector_name"] == frozen.collector_name
            and row["hostname"] == hostname
            and row["egress_key"] == frozen.egress_key
            and row["lane"] == "background"
            and row["retired_at"] is None
        )
        identities_ok = identities_ok and exact
        if row is None:
            print(f"{hostname:<8} MISSING")
            continue
        print(
            f"{hostname:<8} enabled={row['enabled']} drained={row['drained']} "
            f"heartbeat={row['heartbeat_state']} current_job={row['current_job_id']} "
            f"software={row['software_version']!r} exact_identity={exact}"
        )

    expected_events = {
        812: (815, 391, 1),
        813: (816, 392, 1),
        814: (814, 390, 2),
    }
    events_ok = len(events) == 3
    for row in events:
        expected = expected_events.get(int(row["event_id"]))
        exact = expected == (
            int(row["job_id"]), int(row["soldier_id"]), int(row["attempt_number"])
        ) and row["event_type"] == "collection_success" and row["result"] == "success" and row["http_status"] == 200
        events_ok = events_ok and exact
        print(
            f"event={row['event_id']} job={row['job_id']} soldier={row['soldier_id']} "
            f"attempt={row['attempt_number']} collector={row['collector_name_snapshot']} exact={exact}"
        )

    print(f"stable collector identities exact                 {'PASS' if identities_ok else 'FAIL'}")
    print(f"closure events 812..814 exact                     {'PASS' if events_ok else 'FAIL'}")
    print(f"closure jobs 814..816 absent from queue           {'PASS' if not jobs else 'FAIL'}")
    if jobs:
        for row in jobs:
            print(f"  residual job: {dict(row)}")
    print("database writes: 0")
    print("Battlelog requests: 0")
    ok = identities_ok and events_ok and not jobs
    print(f"CLEAN-STOP PREFLIGHT: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
