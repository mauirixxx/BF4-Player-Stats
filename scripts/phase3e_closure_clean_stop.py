#!/usr/bin/env python3
"""Final Phase 3E clean-stop closure for the three frozen collectors.

This harness intentionally creates no collection jobs and makes no Battlelog
requests.  It validates the frozen registry/closure baseline, invokes the
production stop_collector() primitive for each idle collector, then proves the
persistent post-stop state without changing operator-owned controls.
"""
from __future__ import annotations

import os

from sqlalchemy import bindparam, create_engine, text

from bf4ps.collector_runtime import stop_collector
from phase3e_lifecycle_a_common import FROZEN_UUIDS, HOSTS, assert_target

CLOSURE_JOBS = (814, 815, 816)
EXPECTED_EVENTS = {
    812: (815, 391, 1),
    813: (816, 392, 1),
    814: (814, 390, 2),
}


def _database_url() -> str:
    url = os.environ.get("BF4PS_DATABASE_URL")
    if not url:
        raise SystemExit("REFUSING: BF4PS_DATABASE_URL is not set")
    return url


def _collector_rows(conn):
    return conn.execute(
        text("""
            SELECT collector_uuid,collector_name,hostname,lane,egress_key,
                   enabled,drained,heartbeat_state,current_job_id,retired_at
            FROM collectors
            WHERE collector_uuid IN :uuids
            ORDER BY hostname
        """).bindparams(bindparam("uuids", expanding=True)),
        {"uuids": list(FROZEN_UUIDS)},
    ).mappings().all()


def _assert_frozen_idle(rows, *, require_unknown: bool) -> None:
    by_uuid = {row["collector_uuid"]: row for row in rows}
    if len(by_uuid) != 3:
        raise RuntimeError(f"expected three frozen collectors, found {len(by_uuid)}")
    for hostname, frozen in HOSTS.items():
        row = by_uuid.get(frozen.collector_uuid)
        if row is None:
            raise RuntimeError(f"missing frozen collector {hostname}")
        if not (
            row["collector_name"] == frozen.collector_name
            and row["hostname"] == hostname
            and row["lane"] == "background"
            and row["egress_key"] == frozen.egress_key
            and row["retired_at"] is None
            and row["enabled"] is True
            and row["drained"] is False
            and row["current_job_id"] is None
        ):
            raise RuntimeError(f"unexpected collector state for {hostname}: {dict(row)}")
        if require_unknown and row["heartbeat_state"] != "unknown":
            raise RuntimeError(f"collector {hostname} did not persist clean-stop state: {dict(row)}")


def _assert_closure_baseline(conn) -> None:
    jobs = conn.execute(
        text("SELECT job_id FROM collection_jobs WHERE job_id IN :jobs")
        .bindparams(bindparam("jobs", expanding=True)),
        {"jobs": list(CLOSURE_JOBS)},
    ).scalars().all()
    if jobs:
        raise RuntimeError(f"closure jobs unexpectedly remain queued: {jobs}")

    events = conn.execute(text("""
        SELECT event_id,job_id,soldier_id,event_type,attempt_number,result,http_status
        FROM collection_events
        WHERE event_id BETWEEN 812 AND 814
        ORDER BY event_id
    """)).mappings().all()
    if len(events) != 3:
        raise RuntimeError(f"expected closure events 812..814, found {len(events)}")
    for row in events:
        expected = EXPECTED_EVENTS.get(int(row["event_id"]))
        actual = (int(row["job_id"]), int(row["soldier_id"]), int(row["attempt_number"]))
        if not (
            expected == actual
            and row["event_type"] == "collection_success"
            and row["result"] == "success"
            and row["http_status"] == 200
        ):
            raise RuntimeError(f"closure event drift: {dict(row)}")


def main() -> int:
    engine = create_engine(_database_url(), pool_pre_ping=True)

    with engine.begin() as conn:
        assert_target(conn)
        before = _collector_rows(conn)
        _assert_frozen_idle(before, require_unknown=False)
        _assert_closure_baseline(conn)

        print("===== BF4PS PHASE 3E FINAL CLEAN STOP =====", flush=True)
        for row in before:
            print(
                f"before {row['hostname']:<6} heartbeat={row['heartbeat_state']} "
                f"current_job={row['current_job_id']} enabled={row['enabled']} drained={row['drained']}",
                flush=True,
            )

        for hostname, frozen in HOSTS.items():
            if not stop_collector(conn, collector_uuid=frozen.collector_uuid):
                raise RuntimeError(f"production stop_collector failed for {hostname}")
            print(f"stop_collector {hostname}: PASS", flush=True)

    with engine.connect() as conn:
        assert_target(conn)
        after = _collector_rows(conn)
        _assert_frozen_idle(after, require_unknown=True)
        _assert_closure_baseline(conn)
        active_owned = conn.execute(text("""
            SELECT count(*) FROM collection_jobs
            WHERE collector_uuid IN :uuids
              AND status IN ('claimed','running')
        """).bindparams(bindparam("uuids", expanding=True)),
        {"uuids": list(FROZEN_UUIDS)},
        ).scalar_one()
        if int(active_owned) != 0:
            raise RuntimeError(f"frozen collectors still own {active_owned} active jobs")

    for row in after:
        print(
            f"after  {row['hostname']:<6} heartbeat={row['heartbeat_state']} "
            f"current_job={row['current_job_id']} enabled={row['enabled']} drained={row['drained']}"
        )
    print("all three production clean-stop markers persisted: PASS")
    print("all current_job_id values clear: PASS")
    print("operator enabled/drained controls preserved: PASS")
    print("closure events 812..814 preserved: PASS")
    print("closure jobs 814..816 remain absent: PASS")
    print("active jobs owned by frozen collectors: 0")
    print("collection jobs created: 0")
    print("Battlelog requests: 0")
    print("PHASE 3E FINAL CLEAN STOP: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
