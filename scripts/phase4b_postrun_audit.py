#!/usr/bin/env python3
"""Read-only Phase 4B 900-player post-run acceptance audit."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import bindparam, create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parent))

from phase4b_cohort import SOLDIER_IDS
from phase4b_common import EXPECTED_DATABASE, EXPECTED_DB_HOST, FROZEN_UUIDS, HOSTS, assert_target

EXPECTED_ATTEMPTS = 900
EXPECTED_EVENT_FIRST = 905
EXPECTED_EVENT_LAST = 1804


def verdict(label: str, ok: bool, detail: str = "") -> bool:
    suffix = f"  {detail}" if detail else ""
    print(f"{label:<62} {'PASS' if ok else 'FAIL'}{suffix}")
    return ok


def main() -> int:
    url = os.environ.get("BF4PS_DATABASE_URL")
    parsed = urlsplit(url or "")
    if not url or parsed.hostname != EXPECTED_DB_HOST or parsed.path.lstrip("/") != EXPECTED_DATABASE:
        raise SystemExit("REFUSING: wrong or missing BF4PS_DATABASE_URL")

    engine = create_engine(url, pool_pre_ping=True)
    ids = list(SOLDIER_IDS)
    stmt_ids = bindparam("ids", expanding=True)

    with engine.connect() as conn:
        assert_target(conn)

        state_rows = conn.execute(
            text("""
                SELECT detailed_state, count(*)
                FROM collection_state
                WHERE soldier_id IN :ids
                GROUP BY detailed_state
                ORDER BY detailed_state
            """).bindparams(stmt_ids), {"ids": ids}
        ).all()
        state_dist = {str(state): int(count) for state, count in state_rows}

        events = conn.execute(
            text("""
                SELECT event_id, soldier_id, collector_uuid, collector_name_snapshot,
                       hostname_snapshot, egress_key_snapshot, attempt_number, result,
                       http_status, error_class, job_id
                FROM collection_events
                WHERE resource='detailed'
                  AND lane='background'
                  AND soldier_id IN :ids
                ORDER BY event_id
            """).bindparams(stmt_ids), {"ids": ids}
        ).mappings().all()

        successes = [e for e in events if e["result"] == "success"]
        failures = [e for e in events if e["result"] != "success"]
        throttle = [e for e in events if e["http_status"] in (403, 429) or e["error_class"] == "battlelog_throttle"]

        collector_rows = conn.execute(
            text("""
                SELECT collector_uuid, collector_name, hostname, egress_key,
                       heartbeat_state, current_job_id, enabled, drained, retired_at
                FROM collectors
                WHERE collector_uuid IN :uuids
                ORDER BY hostname
            """).bindparams(bindparam("uuids", expanding=True)),
            {"uuids": list(FROZEN_UUIDS)},
        ).mappings().all()

        current_count = int(conn.execute(
            text("SELECT count(*) FROM detailed_stats_current WHERE soldier_id IN :ids").bindparams(stmt_ids),
            {"ids": ids},
        ).scalar_one())
        history_count = int(conn.execute(
            text("SELECT count(*) FROM detailed_stats_history WHERE soldier_id IN :ids").bindparams(stmt_ids),
            {"ids": ids},
        ).scalar_one())
        residual_jobs = int(conn.execute(
            text("SELECT count(*) FROM collection_jobs WHERE resource='detailed' AND soldier_id IN :ids").bindparams(stmt_ids),
            {"ids": ids},
        ).scalar_one())
        foreign_jobs = int(conn.execute(
            text("SELECT count(*) FROM collection_jobs WHERE resource='detailed' AND lane='background' AND soldier_id NOT IN :ids").bindparams(stmt_ids),
            {"ids": ids},
        ).scalar_one())

    event_ids = [int(e["event_id"]) for e in events]
    soldier_event_counts: dict[int, int] = {}
    soldier_success_counts: dict[int, int] = {}
    collector_counts: dict[str, list[int]] = {}
    failure_classes: dict[tuple[object, object], int] = {}

    for e in events:
        sid = int(e["soldier_id"])
        soldier_event_counts[sid] = soldier_event_counts.get(sid, 0) + 1
        if e["result"] == "success":
            soldier_success_counts[sid] = soldier_success_counts.get(sid, 0) + 1
        name = str(e["collector_name_snapshot"])
        bucket = collector_counts.setdefault(name, [0, 0, 0])
        bucket[0] += 1
        if e["result"] == "success":
            bucket[1] += 1
        else:
            bucket[2] += 1
            key = (e["http_status"], e["error_class"])
            failure_classes[key] = failure_classes.get(key, 0) + 1

    expected_names = {f.collector_name for f in HOSTS.values()}
    exact_registry = len(collector_rows) == 3
    for row in collector_rows:
        frozen = HOSTS.get(str(row["hostname"]))
        exact_registry = exact_registry and frozen is not None and str(row["collector_uuid"]) == frozen.collector_uuid and row["collector_name"] == frozen.collector_name and row["egress_key"] == frozen.egress_key

    print("===== BF4PS PHASE 4B 900-PLAYER POST-RUN ACCEPTANCE AUDIT =====")
    print("mode=read-only database reconciliation")
    print(f"frozen cohort: {len(ids)} PC soldiers")
    if event_ids:
        print(f"terminal event span: {min(event_ids)}..{max(event_ids)}")
    print(f"terminal attempts: {len(events)} successes={len(successes)} failures={len(failures)}")
    print(f"state distribution: {state_dist}")

    print("\ncollector distribution:")
    for name in sorted(collector_counts):
        total, good, bad = collector_counts[name]
        print(f"  {name:<20} attempts={total:<4} success={good:<4} failure={bad}")

    print("\nfailure breakdown:")
    if failure_classes:
        for (http, klass), count in sorted(failure_classes.items(), key=lambda item: str(item[0])):
            print(f"  http={http!r:<5} class={klass!r:<30} count={count}")
    else:
        print("  none")

    print("\ncollector registry:")
    for row in collector_rows:
        print(f"  {row['hostname']:<7} {row['collector_name']:<20} heartbeat={row['heartbeat_state']} current_job={row['current_job_id']} enabled={row['enabled']} drained={row['drained']}")

    print("\nacceptance:")
    checks = []
    checks.append(verdict("exactly 900 terminal attempts", len(events) == EXPECTED_ATTEMPTS, str(len(events))))
    checks.append(verdict("terminal event IDs are one contiguous 900-event span", len(event_ids) == EXPECTED_ATTEMPTS and event_ids == list(range(min(event_ids), max(event_ids) + 1)) if event_ids else False, f"{min(event_ids)}..{max(event_ids)}" if event_ids else "none"))
    checks.append(verdict("event span follows Phase 4A closure", bool(event_ids) and min(event_ids) == EXPECTED_EVENT_FIRST and max(event_ids) == EXPECTED_EVENT_LAST, f"expected={EXPECTED_EVENT_FIRST}..{EXPECTED_EVENT_LAST}"))
    checks.append(verdict("all 900 frozen soldiers have exactly one terminal event", len(soldier_event_counts) == 900 and all(v == 1 for v in soldier_event_counts.values()), f"covered={len(soldier_event_counts)}"))
    checks.append(verdict("all terminal attempts succeeded", len(successes) == 900 and not failures, f"success={len(successes)} failure={len(failures)}"))
    checks.append(verdict("all 900 detailed states converged to success", state_dist == {"success": 900}, str(state_dist)))
    checks.append(verdict("900 current rows persisted", current_count == 900, str(current_count)))
    checks.append(verdict("at least 900 history rows persisted", history_count >= 900, str(history_count)))
    checks.append(verdict("zero residual cohort detailed jobs", residual_jobs == 0, str(residual_jobs)))
    checks.append(verdict("zero foreign detailed/background jobs", foreign_jobs == 0, str(foreign_jobs)))
    checks.append(verdict("zero 403/429/throttle events", len(throttle) == 0, str(len(throttle))))
    checks.append(verdict("exactly three frozen collectors participated", set(collector_counts) == expected_names, ",".join(sorted(collector_counts))))
    checks.append(verdict("stable collector registry identities exact", exact_registry))
    checks.append(verdict("all frozen collectors own no current job", all(row["current_job_id"] is None for row in collector_rows)))

    print("\ndatabase writes: 0")
    print("Battlelog requests: 0")
    ok = all(checks)
    print(f"PHASE 4B POST-RUN ACCEPTANCE: {'PASS' if ok else 'INCOMPLETE'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
