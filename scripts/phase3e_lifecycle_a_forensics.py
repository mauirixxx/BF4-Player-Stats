#!/usr/bin/env python3
"""Read-only forensic diagnostics for Phase 3E Lifecycle A reconciliation."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parent))
from phase3e_lifecycle_a_common import (  # noqa: E402
    COHORT_SOLDIER_IDS,
    EXPECTED_DATABASE,
    EXPECTED_DB_HOST,
    FROZEN_UUIDS,
    HOSTS,
    TARGET_HOST,
    assert_target,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--drain-event-id", type=int, required=True)
    parser.add_argument("--undrain-event-id", type=int, required=True)
    args = parser.parse_args()
    if args.undrain_event_id < args.drain_event_id:
        raise SystemExit("REFUSING: undrain boundary precedes drain boundary")

    url = os.environ.get("BF4PS_DATABASE_URL")
    parsed = urlsplit(url or "")
    if (
        not url
        or parsed.hostname != EXPECTED_DB_HOST
        or parsed.path.lstrip("/") != EXPECTED_DATABASE
    ):
        print("REFUSING: wrong database target")
        return 2

    engine = create_engine(url, pool_pre_ping=True)
    ids = list(COHORT_SOLDIER_IDS)
    uuids = list(FROZEN_UUIDS)
    target = HOSTS[TARGET_HOST]

    with engine.connect() as conn:
        assert_target(conn)

        target_window = conn.execute(
            text(
                """
                SELECT event_id, occurred_at, collector_uuid,
                       collector_name_snapshot, hostname_snapshot,
                       egress_key_snapshot, job_id, soldier_id, platform,
                       event_type, attempt_number, result, http_status,
                       error_class
                FROM collection_events
                WHERE resource = 'detailed'
                  AND lane = 'background'
                  AND collector_uuid = :target_uuid
                  AND event_id > :drain_id
                  AND event_id <= :undrain_id
                ORDER BY event_id
                """
            ),
            {
                "target_uuid": target.collector_uuid,
                "drain_id": args.drain_event_id,
                "undrain_id": args.undrain_event_id,
            },
        ).mappings().all()

        foreign_all = conn.execute(
            text(
                """
                SELECT event_id, occurred_at, collector_uuid,
                       collector_name_snapshot, hostname_snapshot,
                       job_id, soldier_id, platform, event_type,
                       attempt_number, result, http_status, error_class
                FROM collection_events
                WHERE resource = 'detailed'
                  AND lane = 'background'
                  AND soldier_id IS NOT NULL
                  AND soldier_id <> ALL(:ids)
                  AND collector_uuid = ANY(:uuids)
                ORDER BY event_id
                """
            ),
            {"ids": ids, "uuids": uuids},
        ).mappings().all()

        cohort_terminal = conn.execute(
            text(
                """
                SELECT min(event_id) AS first_event_id,
                       max(event_id) AS last_event_id,
                       min(occurred_at) AS first_occurred_at,
                       max(occurred_at) AS last_occurred_at
                FROM collection_events
                WHERE resource = 'detailed'
                  AND lane = 'background'
                  AND soldier_id = ANY(:ids)
                  AND collector_uuid = ANY(:uuids)
                  AND event_type IN ('collection_success','collection_failure')
                """
            ),
            {"ids": ids, "uuids": uuids},
        ).mappings().one()

        queue = conn.execute(
            text(
                """
                SELECT job_id, soldier_id, status, priority_class,
                       priority_value, eligible_at, attempt_count,
                       collector_uuid, lease_token, claimed_at, started_at,
                       lease_expires_at, last_error_class, last_error_at,
                       created_at, updated_at
                FROM collection_jobs
                WHERE resource = 'detailed'
                  AND lane = 'background'
                  AND soldier_id = ANY(:ids)
                ORDER BY job_id
                """
            ),
            {"ids": ids},
        ).mappings().all()

    first_event = cohort_terminal["first_event_id"]
    last_event = cohort_terminal["last_event_id"]
    foreign_in_run = [
        row
        for row in foreign_all
        if first_event is not None
        and last_event is not None
        and first_event <= row["event_id"] <= last_event
    ]

    print("===== BF4PS PHASE 3E LIFECYCLE A FORENSICS =====")
    print("READ-ONLY DIAGNOSTIC — database writes: 0; Battlelog requests: 0")
    print(f"drain event-id boundary:   {args.drain_event_id}")
    print(f"undrain event-id boundary: {args.undrain_event_id}")
    print(
        "Lifecycle A terminal event span: "
        f"{first_event}..{last_event} "
        f"({cohort_terminal['first_occurred_at']} .. "
        f"{cohort_terminal['last_occurred_at']})"
    )

    print("\n===== TARGET EVENTS BETWEEN OPERATOR BOUNDARIES =====")
    if not target_window:
        print("(none)")
    for row in target_window:
        print(
            f"event={row['event_id']} at={row['occurred_at']} "
            f"job={row['job_id']} soldier={row['soldier_id']} "
            f"type={row['event_type']} attempt={row['attempt_number']} "
            f"result={row['result']} http={row['http_status']} "
            f"error={row['error_class']}"
        )
    print(f"count between operator boundaries: {len(target_window)}")
    print(
        "NOTE: these are operator event-id proxies; they do not prove the "
        "worker had already observed drained=True."
    )

    print("\n===== ALLEGED OUT-OF-COHORT FROZEN-COLLECTOR EVENTS =====")
    print(f"all historical matching events: {len(foreign_all)}")
    print(f"matching events inside Lifecycle A terminal span: {len(foreign_in_run)}")
    rows = foreign_in_run if foreign_in_run else foreign_all
    if not rows:
        print("(none)")
    else:
        label = "in-run" if foreign_in_run else "historical"
        print(f"showing {label} rows:")
        for row in rows:
            print(
                f"event={row['event_id']} at={row['occurred_at']} "
                f"host={row['hostname_snapshot']} collector={row['collector_uuid']} "
                f"job={row['job_id']} soldier={row['soldier_id']} "
                f"platform={row['platform']} type={row['event_type']} "
                f"attempt={row['attempt_number']} result={row['result']} "
                f"http={row['http_status']} error={row['error_class']}"
            )

    print("\n===== RESIDUAL LIFECYCLE A QUEUE =====")
    if not queue:
        print("(empty)")
    for row in queue:
        print(
            f"job={row['job_id']} soldier={row['soldier_id']} "
            f"status={row['status']} attempt={row['attempt_count']} "
            f"priority={row['priority_class']}/{row['priority_value']} "
            f"eligible={row['eligible_at']} collector={row['collector_uuid']} "
            f"lease={row['lease_token']} claimed={row['claimed_at']} "
            f"started={row['started_at']} expires={row['lease_expires_at']} "
            f"last_error={row['last_error_class']}@{row['last_error_at']}"
        )
    print(f"residual cohort queue rows: {len(queue)}")

    print("\nFORENSIC COLLECTION COMPLETE — NO MUTATIONS PERFORMED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
