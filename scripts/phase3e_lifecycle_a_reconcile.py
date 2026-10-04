#!/usr/bin/env python3
"""Read-only final reconciliation for Phase 3E Lifecycle A."""
from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parent))
from phase3e_lifecycle_a_common import *  # noqa: E402,F403


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--drain-event-id", type=int, required=True)
    parser.add_argument("--drain-ack-event-id", type=int, required=True)
    parser.add_argument("--undrain-event-id", type=int, required=True)
    args = parser.parse_args()
    if not args.drain_event_id <= args.drain_ack_event_id <= args.undrain_event_id:
        raise SystemExit("REFUSING: expected drain <= drain acknowledgement <= undrain")

    url = os.environ.get("BF4PS_DATABASE_URL")
    parsed = urlsplit(url or "")
    if not url or parsed.hostname != EXPECTED_DB_HOST or parsed.path.lstrip("/") != EXPECTED_DATABASE:
        print("REFUSING: wrong database target")
        return 2

    engine = create_engine(url, pool_pre_ping=True)
    ids = list(COHORT_SOLDIER_IDS)
    uuids = list(FROZEN_UUIDS)
    target = HOSTS[TARGET_HOST]

    with engine.connect() as conn:
        assert_target(conn)
        terminal = conn.execute(text("""
            SELECT event_id, collector_uuid, hostname_snapshot, egress_key_snapshot,
                   soldier_id, platform, event_type, attempt_number, error_class
            FROM collection_events
            WHERE resource='detailed' AND lane='background'
              AND soldier_id=ANY(:ids) AND collector_uuid=ANY(:uuids)
              AND event_type IN ('collection_success','collection_failure')
            ORDER BY event_id
        """), {"ids": ids, "uuids": uuids}).mappings().all()

        first_event_id = int(terminal[0]["event_id"]) if terminal else 0
        last_event_id = int(terminal[-1]["event_id"]) if terminal else 0
        foreign_in_run = int(conn.execute(text("""
            SELECT count(*) FROM collection_events
            WHERE resource='detailed' AND lane='background'
              AND soldier_id IS NOT NULL AND soldier_id<>ALL(:ids)
              AND collector_uuid=ANY(:uuids)
              AND event_id BETWEEN :first_id AND :last_id
        """), {"ids": ids, "uuids": uuids, "first_id": first_event_id,
                 "last_id": last_event_id}).scalar_one())
        queue = conn.execute(text("""
            SELECT job_id, soldier_id, status, attempt_count, collector_uuid,
                   lease_token, claimed_at, started_at, lease_expires_at,
                   last_error_class
            FROM collection_jobs
            WHERE resource='detailed' AND lane='background' AND soldier_id=ANY(:ids)
            ORDER BY job_id
        """), {"ids": ids}).mappings().all()
        collectors = conn.execute(text("""
            SELECT collector_uuid, hostname, egress_key, drained, current_job_id,
                   heartbeat_state FROM collectors WHERE collector_uuid=ANY(:uuids)
        """), {"uuids": uuids}).mappings().all()

    per = Counter(row["collector_uuid"] for row in terminal)
    soldiers = Counter(int(row["soldier_id"]) for row in terminal)
    failures = {int(row["soldier_id"]): row for row in terminal
                if row["event_type"] == "collection_failure"}
    target_pre_ack = [row for row in terminal
                      if row["collector_uuid"] == target.collector_uuid
                      and args.drain_event_id < int(row["event_id"]) <= args.drain_ack_event_id]
    target_while_drained = [row for row in terminal
                            if row["collector_uuid"] == target.collector_uuid
                            and args.drain_ack_event_id < int(row["event_id"]) <= args.undrain_event_id]
    target_after = [row for row in terminal
                    if row["collector_uuid"] == target.collector_uuid
                    and int(row["event_id"]) > args.undrain_event_id]
    survivor_during = [row for row in terminal
                       if row["collector_uuid"] != target.collector_uuid
                       and args.drain_ack_event_id < int(row["event_id"]) <= args.undrain_event_id]
    identities = all(row["collector_uuid"] in FROZEN_UUIDS
                     and row["hostname_snapshot"] in HOSTS
                     and row["egress_key_snapshot"] == HOSTS[row["hostname_snapshot"]].egress_key
                     for row in terminal)

    residual = {int(row["soldier_id"]): row for row in queue}
    residual_retry_shape = set(residual) == set(failures) and all(
        row["status"] == "pending" and int(row["attempt_count"]) == 1
        and row["collector_uuid"] is None and row["lease_token"] is None
        and row["claimed_at"] is None and row["started_at"] is None
        and row["lease_expires_at"] is None
        and row["last_error_class"] == failures[soldier_id]["error_class"]
        for soldier_id, row in residual.items()
    )

    checks = {
        "exactly 360 terminal attempts": len(terminal) == 360,
        "each frozen soldier exactly once": len(soldiers) == 360 and all(v == 1 for v in soldiers.values()),
        "all three progressed": all(per[h.collector_uuid] > 0 for h in HOSTS.values()),
        "drain acknowledgement bounded": len(target_pre_ack) <= 1,
        "target quiet after drain acknowledgement": not target_while_drained,
        "survivors progressed while target drained": len(survivor_during) > 0,
        "target progressed after explicit undrain": len(target_after) > 0,
        "event identity snapshots exact": identities,
        "no frozen-collector work outside cohort in run": foreign_in_run == 0,
        "residual queue exactly matches retryable failures": residual_retry_shape,
        "collectors own no current job": all(row["current_job_id"] is None for row in collectors),
    }

    print("===== BF4PS PHASE 3E LIFECYCLE A RECONCILIATION =====")
    print(f"Lifecycle A terminal span: {first_event_id}..{last_event_id}")
    print(f"drain operator event_id:   {args.drain_event_id}")
    print(f"drain ack event_id:        {args.drain_ack_event_id}")
    print(f"undrain event_id:          {args.undrain_event_id}")
    for hostname, host in HOSTS.items():
        print(f"{hostname:<8} terminal={per[host.collector_uuid]}")
    print(f"terminal failures:          {len(failures)}")
    print(f"residual retry rows:        {len(queue)}")
    print(f"foreign in-run events:      {foreign_in_run}")
    print(f"target pre-ack terminals:   {len(target_pre_ack)}")
    for key, value in checks.items():
        print(f'{key:<52} {"PASS" if value else "FAIL"}')
    ok = all(checks.values())
    print(f'\nLIFECYCLE A RECONCILIATION: {"PASS" if ok else "FAIL"}')
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
