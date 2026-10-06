#!/usr/bin/env python3
"""Read-only Phase 4C multiplatform sustained-run acceptance audit."""
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from sqlalchemy import bindparam, text

from bf4ps.db import make_engine
from phase4c_cohort import PHASE4C_COHORT, SOLDIER_IDS
from phase4c_common import HOSTS

EXPECTED_TOTAL = 450
EXPECTED_PER_PLATFORM = {"pc": 150, "ps4": 150, "xboxone": 150}
EXPECTED_COLLECTOR_NAMES = {host.collector_name for host in HOSTS.values()}


def mark(label: str, ok: bool, detail: str = "") -> bool:
    suffix = f"  {detail}" if detail else ""
    print(f"{label:<66} {'PASS' if ok else 'FAIL'}{suffix}")
    return ok


def main() -> int:
    engine = make_engine()
    expected_by_id = {row[0]: row for row in PHASE4C_COHORT}
    ids = list(SOLDIER_IDS)
    params = {"ids": ids}

    with engine.connect() as conn:
        events = conn.execute(
            text("""
                SELECT event_id, occurred_at, collector_name_snapshot,
                       hostname_snapshot, egress_key_snapshot, job_id,
                       soldier_id, persona_id, platform, result,
                       http_status, error_class, error_message
                FROM collection_events
                WHERE resource = 'detailed'
                  AND soldier_id IN :ids
                  AND result IN ('success', 'failure')
                ORDER BY event_id
            """).bindparams(bindparam("ids", expanding=True)), params,
        ).mappings().all()

        states = conn.execute(
            text("""
                SELECT soldier_id, detailed_state, detailed_last_attempt_at,
                       detailed_last_success_at, detailed_consecutive_failures,
                       detailed_last_error_class, detailed_last_error_message
                FROM collection_state
                WHERE soldier_id IN :ids
            """).bindparams(bindparam("ids", expanding=True)), params,
        ).mappings().all()

        current_ids = set(conn.execute(
            text("SELECT soldier_id FROM detailed_stats_current WHERE soldier_id IN :ids")
            .bindparams(bindparam("ids", expanding=True)), params,
        ).scalars())

        history_counts = dict(conn.execute(
            text("""
                SELECT soldier_id, count(*)
                FROM detailed_stats_history
                WHERE soldier_id IN :ids
                GROUP BY soldier_id
            """).bindparams(bindparam("ids", expanding=True)), params,
        ).all())

        residual_jobs = conn.execute(
            text("""
                SELECT count(*) FROM collection_jobs
                WHERE resource = 'detailed' AND soldier_id IN :ids
            """).bindparams(bindparam("ids", expanding=True)), params,
        ).scalar_one()

        foreign_jobs = conn.execute(text("""
            SELECT count(*) FROM collection_jobs
            WHERE resource = 'detailed' AND soldier_id NOT IN :ids
        """).bindparams(bindparam("ids", expanding=True)), params).scalar_one()

        throttle_count = conn.execute(text("""
            SELECT count(*) FROM collection_events
            WHERE http_status IN (403, 429)
        """)).scalar_one()

        collectors = conn.execute(text("""
            SELECT collector_name, hostname, heartbeat_state, current_job_id,
                   enabled, drained, retired_at
            FROM collectors
            WHERE collector_name IN ('phase3e-hnl-01','phase3e-kah-01','phase3e-tcou')
            ORDER BY collector_name
        """)).all()

    event_counts = Counter(e["result"] for e in events)
    platform_attempts = Counter(e["platform"] for e in events)
    platform_success = Counter(e["platform"] for e in events if e["result"] == "success")
    platform_failure = Counter(e["platform"] for e in events if e["result"] == "failure")
    collector_counts = Counter(e["collector_name_snapshot"] for e in events)
    failure_breakdown = Counter((e["platform"], e["http_status"], e["error_class"]) for e in events if e["result"] == "failure")
    events_by_soldier = defaultdict(list)
    for e in events:
        events_by_soldier[e["soldier_id"]].append(e)

    state_by_id = {r["soldier_id"]: r for r in states}
    state_counts = Counter(r["detailed_state"] for r in states)
    success_ids = {e["soldier_id"] for e in events if e["result"] == "success"}
    failure_ids = {e["soldier_id"] for e in events if e["result"] == "failure"}

    identity_ok = all(
        e["soldier_id"] in expected_by_id
        and e["persona_id"] == expected_by_id[e["soldier_id"]][1]
        and e["platform"] == expected_by_id[e["soldier_id"]][3]
        for e in events
    )
    exactly_one = len(events_by_soldier) == EXPECTED_TOTAL and all(len(v) == 1 for v in events_by_soldier.values())
    state_matches = all(
        state_by_id.get(sid, {}).get("detailed_state") == "success"
        for sid in success_ids
    ) and all(
        state_by_id.get(sid, {}).get("detailed_state") in {"never_attempted", "temporary_failure", "unavailable"}
        for sid in failure_ids
    )
    persistence_ok = success_ids <= current_ids and all(history_counts.get(sid, 0) >= 1 for sid in success_ids)
    failure_no_current = not (failure_ids & current_ids)

    print("===== BF4PS PHASE 4C MULTIPLATFORM POST-RUN ACCEPTANCE AUDIT =====")
    print("mode=read-only database reconciliation")
    print(f"frozen cohort: {EXPECTED_TOTAL} soldiers {EXPECTED_PER_PLATFORM}")
    if events:
        print(f"terminal event span: {events[0]['event_id']}..{events[-1]['event_id']}")
    print(f"terminal attempts: {len(events)} successes={event_counts['success']} failures={event_counts['failure']}")
    print(f"state distribution: {dict(sorted(state_counts.items()))}")

    print("\nplatform distribution:")
    for platform in ("pc", "ps4", "xboxone"):
        print(f"  {platform:<8} attempts={platform_attempts[platform]:<3} success={platform_success[platform]:<3} failure={platform_failure[platform]}")

    print("\ncollector distribution:")
    for name in sorted(EXPECTED_COLLECTOR_NAMES):
        print(f"  {name:<20} attempts={collector_counts[name]}")

    print("\nfailure breakdown:")
    if not failure_breakdown:
        print("  none")
    else:
        for (platform, http_status, error_class), count in sorted(failure_breakdown.items(), key=lambda x: str(x[0])):
            print(f"  platform={platform:<8} http={http_status!s:<4} class={error_class!r:<28} count={count}")
        print("\nfailure details:")
        for e in (x for x in events if x["result"] == "failure"):
            expected = expected_by_id[e["soldier_id"]]
            print(f"  soldier={e['soldier_id']} persona={e['persona_id']} name={expected[2]!r} platform={e['platform']} collector={e['collector_name_snapshot']} job={e['job_id']} event={e['event_id']} http={e['http_status']} class={e['error_class']!r} error={e['error_message']!r}")

    print("\ncollector registry:")
    for row in collectors:
        print(f"  {row.collector_name:<20} host={row.hostname:<7} heartbeat={row.heartbeat_state} current_job={row.current_job_id} enabled={row.enabled} drained={row.drained} retired={row.retired_at}")

    checks = []
    print("\nacceptance:")
    checks.append(mark("exactly 450 terminal attempts", len(events) == EXPECTED_TOTAL, str(len(events))))
    checks.append(mark("exact 150/150/150 terminal platform distribution", dict(platform_attempts) == EXPECTED_PER_PLATFORM, str(dict(platform_attempts))))
    checks.append(mark("all frozen soldiers have exactly one terminal event", exactly_one, f"covered={len(events_by_soldier)}"))
    checks.append(mark("terminal event identity/platform matches frozen cohort", identity_ok))
    checks.append(mark("collection state agrees with terminal result", state_matches, str(dict(state_counts))))
    checks.append(mark("every successful soldier has current + history persistence", persistence_ok, f"success={len(success_ids)}"))
    checks.append(mark("failed soldiers have no detailed current row", failure_no_current, f"failures={len(failure_ids)}"))
    checks.append(mark("zero residual cohort detailed jobs", residual_jobs == 0, str(residual_jobs)))
    checks.append(mark("zero foreign detailed jobs", foreign_jobs == 0, str(foreign_jobs)))
    checks.append(mark("zero 403/429 throttle events", throttle_count == 0, str(throttle_count)))
    checks.append(mark("exactly three frozen collectors participated", set(collector_counts) == EXPECTED_COLLECTOR_NAMES, ",".join(sorted(collector_counts))))
    checks.append(mark("stable collector registry identities present", {r.collector_name for r in collectors} == EXPECTED_COLLECTOR_NAMES))
    checks.append(mark("all frozen collectors own no current job", all(r.current_job_id is None for r in collectors)))

    print("\ndatabase writes: 0")
    print("Battlelog requests: 0")
    accepted = all(checks)
    print(f"PHASE 4C MULTIPLATFORM POST-RUN ACCEPTANCE: {'PASS' if accepted else 'INCOMPLETE'}")
    return 0 if accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
