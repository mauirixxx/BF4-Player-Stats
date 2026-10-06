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
ATTEMPT_EVENT_TYPES = {"collection_success", "collection_failure"}


def mark(label: str, ok: bool, detail: str = "") -> bool:
    suffix = f"  {detail}" if detail else ""
    print(f"{label:<70} {'PASS' if ok else 'FAIL'}{suffix}")
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
                       soldier_id, persona_id, platform, event_type, result,
                       attempt_number, http_status, error_class, error_message
                FROM collection_events
                WHERE resource = 'detailed'
                  AND soldier_id IN :ids
                  AND event_type IN ('collection_success', 'collection_failure')
                ORDER BY event_id
            """).bindparams(bindparam("ids", expanding=True)), params,
        ).mappings().all()

        states = conn.execute(
            text("""
                SELECT soldier_id, detailed_state, detailed_last_attempt_at,
                       detailed_last_success_at, detailed_next_due_at,
                       detailed_consecutive_failures,
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

        cohort_jobs = conn.execute(
            text("""
                SELECT job_id, soldier_id, status, attempt_count, collector_uuid,
                       lease_token, claimed_at, started_at, lease_expires_at,
                       eligible_at, last_error_class, last_error_at
                FROM collection_jobs
                WHERE resource = 'detailed' AND soldier_id IN :ids
                ORDER BY job_id
            """).bindparams(bindparam("ids", expanding=True)), params,
        ).mappings().all()

        foreign_jobs = conn.execute(text("""
            SELECT count(*) FROM collection_jobs
            WHERE resource = 'detailed' AND soldier_id NOT IN :ids
        """).bindparams(bindparam("ids", expanding=True)), params).scalar_one()

        throttle_count = conn.execute(text("""
            SELECT count(*) FROM collection_events
            WHERE http_status IN (403, 429)
               OR error_class = 'battlelog_throttle'
        """)).scalar_one()

        collectors = conn.execute(text("""
            SELECT collector_name, hostname, heartbeat_state, current_job_id,
                   enabled, drained, retired_at
            FROM collectors
            WHERE collector_name IN ('phase3e-hnl-01','phase3e-kah-01','phase3e-tcou')
            ORDER BY collector_name
        """)).all()

    event_type_counts = Counter(e["event_type"] for e in events)
    result_counts = Counter(e["result"] for e in events)
    platform_attempts = Counter(e["platform"] for e in events)
    platform_success = Counter(e["platform"] for e in events if e["event_type"] == "collection_success")
    platform_failure = Counter(e["platform"] for e in events if e["event_type"] == "collection_failure")
    collector_counts = Counter(e["collector_name_snapshot"] for e in events)
    failure_breakdown = Counter(
        (e["platform"], e["result"], e["http_status"], e["error_class"])
        for e in events if e["event_type"] == "collection_failure"
    )
    events_by_soldier = defaultdict(list)
    for e in events:
        events_by_soldier[e["soldier_id"]].append(e)

    state_by_id = {r["soldier_id"]: r for r in states}
    state_counts = Counter(r["detailed_state"] for r in states)
    success_ids = {e["soldier_id"] for e in events if e["event_type"] == "collection_success"}
    latest_event_by_soldier = {sid: soldier_events[-1] for sid, soldier_events in events_by_soldier.items()}
    unresolved_failure_ids = {
        sid for sid, event in latest_event_by_soldier.items()
        if event["event_type"] == "collection_failure"
    }
    never_attempted_ids = set(ids) - set(events_by_soldier)

    identity_ok = all(
        e["soldier_id"] in expected_by_id
        and e["persona_id"] == expected_by_id[e["soldier_id"]][1]
        and e["platform"] == expected_by_id[e["soldier_id"]][3]
        for e in events
    )
    event_shape_ok = all(
        (e["event_type"] == "collection_success" and e["result"] == "success")
        or (e["event_type"] == "collection_failure" and e["result"] in {"temporary_failure", "unavailable"})
        for e in events
    )
    contiguous_event_ids = bool(events) and [e["event_id"] for e in events] == list(
        range(events[0]["event_id"], events[0]["event_id"] + len(events))
    )
    latest_state_ok = all(
        state_by_id.get(sid, {}).get("detailed_state") == (
            "success" if event["event_type"] == "collection_success" else event["result"]
        )
        for sid, event in latest_event_by_soldier.items()
    ) and all(
        state_by_id.get(sid, {}).get("detailed_state") == "never_attempted"
        for sid in never_attempted_ids
    )
    persistence_ok = success_ids <= current_ids and all(history_counts.get(sid, 0) >= 1 for sid in success_ids)
    unresolved_no_current = not (unresolved_failure_ids & current_ids)

    job_ids = {j["soldier_id"] for j in cohort_jobs}
    expected_retry_ids = {
        sid for sid in unresolved_failure_ids
        if state_by_id.get(sid, {}).get("detailed_state") == "temporary_failure"
    }
    retry_jobs_match = job_ids == expected_retry_ids
    retry_jobs_pending_unowned = all(
        j["status"] == "pending"
        and j["collector_uuid"] is None
        and j["lease_token"] is None
        and j["claimed_at"] is None
        and j["started_at"] is None
        and j["lease_expires_at"] is None
        for j in cohort_jobs
    )

    print("===== BF4PS PHASE 4C MULTIPLATFORM POST-RUN ACCEPTANCE AUDIT =====")
    print("mode=read-only database reconciliation")
    print(f"frozen cohort: {EXPECTED_TOTAL} soldiers {EXPECTED_PER_PLATFORM}")
    if events:
        print(f"collection-attempt event span: {events[0]['event_id']}..{events[-1]['event_id']}")
    print(
        f"collection attempts: {len(events)} "
        f"success={event_type_counts['collection_success']} "
        f"temporary_failure={result_counts['temporary_failure']} "
        f"unavailable={result_counts['unavailable']}"
    )
    print(f"unique soldiers attempted: {len(events_by_soldier)}")
    print(f"state distribution: {dict(sorted(state_counts.items()))}")

    print("\nplatform attempt distribution:")
    for platform in ("pc", "ps4", "xboxone"):
        print(
            f"  {platform:<8} attempts={platform_attempts[platform]:<3} "
            f"success_events={platform_success[platform]:<3} "
            f"failure_events={platform_failure[platform]}"
        )

    print("\ncollector distribution:")
    for name in sorted(EXPECTED_COLLECTOR_NAMES):
        print(f"  {name:<20} attempts={collector_counts[name]}")

    print("\nfailure breakdown:")
    if not failure_breakdown:
        print("  none")
    else:
        for (platform, result, http_status, error_class), count in sorted(failure_breakdown.items(), key=lambda x: str(x[0])):
            print(
                f"  platform={platform:<8} result={result!r:<20} "
                f"http={http_status!s:<4} class={error_class!r:<28} count={count}"
            )
        print("\nunresolved failure details:")
        if not unresolved_failure_ids:
            print("  none")
        for sid in sorted(unresolved_failure_ids):
            e = latest_event_by_soldier[sid]
            expected = expected_by_id[sid]
            print(
                f"  soldier={sid} persona={e['persona_id']} name={expected[2]!r} "
                f"platform={e['platform']} collector={e['collector_name_snapshot']} "
                f"job={e['job_id']} event={e['event_id']} result={e['result']} "
                f"http={e['http_status']} class={e['error_class']!r} error={e['error_message']!r}"
            )

    print("\nresidual cohort jobs:")
    if not cohort_jobs:
        print("  none")
    for j in cohort_jobs:
        print(
            f"  job={j['job_id']} soldier={j['soldier_id']} status={j['status']} "
            f"attempt={j['attempt_count']} eligible={j['eligible_at']} "
            f"class={j['last_error_class']!r} owner={j['collector_uuid']}"
        )

    print("\ncollector registry:")
    for row in collectors:
        print(
            f"  {row.collector_name:<20} host={row.hostname:<7} "
            f"heartbeat={row.heartbeat_state} current_job={row.current_job_id} "
            f"enabled={row.enabled} drained={row.drained} retired={row.retired_at}"
        )

    checks = []
    print("\nacceptance:")
    checks.append(mark("exactly 450 collection attempts recorded", len(events) == EXPECTED_TOTAL, str(len(events))))
    checks.append(mark("450 attempt event IDs form one contiguous span", contiguous_event_ids, f"{events[0]['event_id']}..{events[-1]['event_id']}" if events else "none"))
    checks.append(mark("attempt event/result shapes are lifecycle-valid", event_shape_ok, str(dict(result_counts))))
    checks.append(mark("attempt event identity/platform matches frozen cohort", identity_ok))
    checks.append(mark("all three frozen platforms were exercised", set(platform_attempts) == set(EXPECTED_PER_PLATFORM), str(dict(platform_attempts))))
    checks.append(mark("no platform exceeds its 150-soldier success ceiling", all(platform_success[p] <= 150 for p in EXPECTED_PER_PLATFORM), str(dict(platform_success))))
    checks.append(mark("collection state agrees with each soldier's latest attempt", latest_state_ok, str(dict(state_counts))))
    checks.append(mark("every successful soldier has current + history persistence", persistence_ok, f"successful_soldiers={len(success_ids)}"))
    checks.append(mark("unresolved failed soldiers have no detailed current row", unresolved_no_current, f"unresolved={len(unresolved_failure_ids)}"))
    checks.append(mark("residual cohort jobs exactly match temporary failures", retry_jobs_match, f"jobs={sorted(job_ids)} retry={sorted(expected_retry_ids)}"))
    checks.append(mark("residual retry jobs are pending and unowned", retry_jobs_pending_unowned, str(len(cohort_jobs))))
    checks.append(mark("zero foreign detailed jobs", foreign_jobs == 0, str(foreign_jobs)))
    checks.append(mark("zero 403/429/throttle events", throttle_count == 0, str(throttle_count)))
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
