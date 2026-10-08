#!/usr/bin/env python3
"""Read-only production checkpoint audit for Phase 5B Step 9."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta

from sqlalchemy import create_engine, text

from bf4ps.config import database_url
from bf4ps.production_hosts import COLLECTOR_UUIDS, RESOURCES

EXPECTED_DATABASE = "bf4_playerstats_test"
EXPECTED_REVISION = "0003_request_gates"
BACKGROUND_HOURLY_CEILING = 1296


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cutover-at",
        required=True,
        help="Timezone-aware production materialization cutover timestamp.",
    )
    parser.add_argument(
        "--since-event-id",
        type=int,
        required=True,
        help="Exclusive collection_events boundary recorded at production activation.",
    )
    args = parser.parse_args()
    if args.since_event_id < 0:
        raise SystemExit("--since-event-id must be non-negative")
    try:
        cutover = datetime.fromisoformat(args.cutover_at)
    except ValueError as exc:
        raise SystemExit("--cutover-at must be a valid ISO-8601 timestamp") from exc
    if cutover.tzinfo is None or cutover.utcoffset() is None:
        raise SystemExit("--cutover-at must include a timezone offset")

    engine = create_engine(database_url(), pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            db = conn.execute(text("SELECT current_database()")).scalar_one()
            revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            recovery = bool(conn.execute(text("SELECT pg_is_in_recovery()")).scalar_one())
            read_only = conn.execute(text("SELECT current_setting('transaction_read_only')")).scalar_one()
            if db != EXPECTED_DATABASE or revision != EXPECTED_REVISION or recovery or read_only != "off":
                raise RuntimeError(
                    f"wrong target db={db!r} revision={revision!r} recovery={recovery} read_only={read_only!r}"
                )

            starts = conn.execute(text("""
                SELECT event_id,occurred_at,collector_uuid,collector_name_snapshot,
                       egress_key_snapshot,job_id,soldier_id,platform,resource,
                       attempt_number
                FROM collection_events
                WHERE event_id>:boundary
                  AND lane='background'
                  AND event_type='collection_attempt_started'
                  AND resource=ANY(:resources)
                ORDER BY occurred_at,event_id
            """), {"boundary": args.since_event_id, "resources": list(RESOURCES)}).mappings().all()
            terminals = conn.execute(text("""
                SELECT event_id,job_id,resource,attempt_number,event_type,result,http_status,error_class
                FROM collection_events
                WHERE event_id>:boundary
                  AND lane='background'
                  AND event_type IN ('collection_success','collection_failure')
                  AND resource=ANY(:resources)
                ORDER BY event_id
            """), {"boundary": args.since_event_id, "resources": list(RESOURCES)}).mappings().all()

            start_keys = [(int(r["job_id"]), int(r["attempt_number"])) for r in starts]
            terminal_keys = [(int(r["job_id"]), int(r["attempt_number"])) for r in terminals]
            start_set = set(start_keys)
            terminal_set = set(terminal_keys)
            duplicate_starts = len(start_keys) - len(start_set)
            duplicate_terminals = len(terminal_keys) - len(terminal_set)
            attempts_without_terminal = len(start_set - terminal_set)
            terminals_without_start = len(terminal_set - start_set)

            rolling_max = 0
            left = 0
            times = [r["occurred_at"] for r in starts]
            for right, stamp in enumerate(times):
                cutoff = stamp - timedelta(hours=1)
                while left <= right and times[left] <= cutoff:
                    left += 1
                rolling_max = max(rolling_max, right - left + 1)

            abort_events = int(conn.execute(text("""
                SELECT COUNT(*) FROM collection_events
                WHERE event_id>:boundary
                  AND (
                    event_type='collection_persistence_failure'
                    OR http_status IN (403,429)
                    OR error_class='battlelog_throttle'
                  )
            """), {"boundary": args.since_event_id}).scalar_one())

            foreign = sum(
                1 for r in starts
                if r["collector_uuid"] not in COLLECTOR_UUIDS
            )
            successes = sum(1 for r in terminals if r["event_type"] == "collection_success")
            failures = sum(1 for r in terminals if r["event_type"] == "collection_failure")

            by_resource = {resource: 0 for resource in RESOURCES}
            by_collector: dict[str, int] = {}
            for row in starts:
                by_resource[str(row["resource"])] += 1
                name = str(row["collector_name_snapshot"])
                by_collector[name] = by_collector.get(name, 0) + 1

            queue = conn.execute(text("""
                SELECT lane,priority_class,reason,status,COUNT(*) AS n
                FROM collection_jobs
                GROUP BY lane,priority_class,reason,status
                ORDER BY lane,priority_class,reason,status
            """)).mappings().all()
            owned = int(conn.execute(text("""
                SELECT COUNT(*) FROM collection_jobs
                WHERE status IN ('claimed','running')
            """)).scalar_one())
            bad_provenance = int(conn.execute(text("""
                SELECT COUNT(*) FROM collection_jobs
                WHERE lane='background'
                  AND resource=ANY(:resources)
                  AND (
                    reason NOT IN ('bf4sw_new_soldier','bf4sw_active_refresh')
                    OR eligible_at < :cutover
                  )
            """), {"resources": list(RESOURCES), "cutover": cutover}).scalar_one())

        print("===== BF4PS PHASE 5B STEP 9 PRODUCTION CHECKPOINT AUDIT =====")
        print(f"database={db} revision={revision} primary_writable=yes boundary_event_id={args.since_event_id}")
        print(f"materialization_cutover_at={cutover.isoformat()}")
        print(
            f"physical_attempts={len(starts)} terminal_events={len(terminals)} "
            f"success={successes} failure={failures}"
        )
        print(
            f"duplicate_attempt_keys={duplicate_starts} duplicate_terminal_keys={duplicate_terminals} "
            f"attempts_without_terminal={attempts_without_terminal} terminals_without_start={terminals_without_start}"
        )
        print(
            "by_resource=" + ",".join(f"{k}:{v}" for k, v in by_resource.items())
        )
        print(
            "by_collector=" + ",".join(f"{k}:{v}" for k, v in sorted(by_collector.items()))
        )
        print(f"rolling_1h_max_physical_starts={rolling_max} ceiling={BACKGROUND_HOURLY_CEILING}")
        print(f"403_429_throttle_or_persistence={abort_events} foreign_physical_starts={foreign}")
        print(f"claimed_or_running_jobs_now={owned} bad_background_job_provenance={bad_provenance}")
        for row in queue:
            print(
                f"  QUEUE lane={row['lane']} priority={row['priority_class']} "
                f"reason={row['reason']} status={row['status']} count={row['n']}"
            )
        print("database writes: 0")
        print("Battlelog requests by audit: 0")

        passed = (
            duplicate_starts == 0
            and duplicate_terminals == 0
            and attempts_without_terminal == 0
            and terminals_without_start == 0
            and rolling_max <= BACKGROUND_HOURLY_CEILING
            and abort_events == 0
            and foreign == 0
            and bad_provenance == 0
        )
        print(
            "PHASE 5B STEP 9 PRODUCTION CHECKPOINT AUDIT: "
            + ("PASS" if passed else "FAIL")
        )
        return 0 if passed else 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
