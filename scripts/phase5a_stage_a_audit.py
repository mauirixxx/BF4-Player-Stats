#!/usr/bin/env python3
"""Read-only post-run audit for Phase 5A Stage A weapon characterization."""
from __future__ import annotations

from collections import Counter
from statistics import mean, median

from sqlalchemy import text

from bf4ps.db import make_engine
from bf4ps.phase5a_frozen_cohort import FROZEN_COHORT
from phase5a_stage_a_common import FROZEN_UUIDS, GLOBAL_ATTEMPT_CEILING, SOLDIER_IDS, assert_target

def check(label, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"{label:<72} {status}" + (f"  {detail}" if detail else ""))
    if not condition:
        raise AssertionError(f"{label}: {detail or 'condition was false'}")

def main() -> int:
    print("===== BF4PS PHASE 5A STAGE A POST-RUN AUDIT =====")
    print("database writes: 0")
    print("Battlelog requests: 0")
    engine = make_engine()
    with engine.connect() as conn:
        assert_target(conn)
        starts = conn.execute(text("""
            SELECT event_id, job_id, soldier_id, persona_id, platform, collector_uuid,
                   attempt_number, lease_token, metadata
            FROM collection_events
            WHERE resource='weapons' AND lane='background'
              AND soldier_id=ANY(:ids)
              AND event_type='collection_attempt_started'
            ORDER BY event_id
        """), {"ids": list(SOLDIER_IDS)}).mappings().all()

        events = conn.execute(text("""
            SELECT event_id, job_id, soldier_id, persona_id, platform, collector_uuid,
                   event_type, attempt_number, result, duration_ms, http_status,
                   error_class, metadata
            FROM collection_events
            WHERE resource='weapons' AND lane='background'
              AND soldier_id=ANY(:ids)
              AND event_type IN ('collection_success','collection_failure')
            ORDER BY event_id
        """), {"ids": list(SOLDIER_IDS)}).mappings().all()

        check("exactly 30 durable physical weapon attempts exist",
              len(starts) == GLOBAL_ATTEMPT_CEILING, str(len(starts)))
        start_counts = Counter(int(e["soldier_id"]) for e in starts)
        check("exactly one physical attempt exists per frozen soldier",
              set(start_counts) == set(SOLDIER_IDS) and all(v == 1 for v in start_counts.values()),
              str(dict(start_counts)))
        check("all three frozen collectors participated in physical attempts",
              {e["collector_uuid"] for e in starts} == set(FROZEN_UUIDS),
              str(sorted(str(e["collector_uuid"]) for e in starts)))
        check("exactly 30 terminal weapon attempt events exist", len(events) == GLOBAL_ATTEMPT_CEILING, str(len(events)))
        counts = Counter(int(e["soldier_id"]) for e in events)
        check("exactly one terminal event exists per frozen soldier",
              set(counts) == set(SOLDIER_IDS) and all(v == 1 for v in counts.values()), str(dict(counts)))
        start_keys = {(int(e["job_id"]), int(e["attempt_number"])) for e in starts}
        terminal_keys = {(int(e["job_id"]), int(e["attempt_number"])) for e in events}
        check("every physical attempt has exactly one durable terminal outcome",
              start_keys == terminal_keys,
              f"starts={len(start_keys)} terminals={len(terminal_keys)}")
        check("event platform split is exactly 10/10/10",
              Counter(str(e["platform"]) for e in events) == Counter({"pc":10,"ps4":10,"xboxone":10}))
        check("no 403/429/throttle evidence",
              not any(e["http_status"] in {403,429} or e["error_class"] == "battlelog_throttle" for e in events))

        jobs = conn.execute(text("""
            SELECT job_id, soldier_id, status, attempt_count, last_error_class
            FROM collection_jobs
            WHERE resource='weapons' AND soldier_id=ANY(:ids)
            ORDER BY soldier_id
        """), {"ids": list(SOLDIER_IDS)}).mappings().all()

        states = conn.execute(text("""
            SELECT soldier_id, weapons_state, weapons_consecutive_failures,
                   weapons_last_error_class, weapons_last_error_message
            FROM collection_state WHERE soldier_id=ANY(:ids)
            ORDER BY soldier_id
        """), {"ids": list(SOLDIER_IDS)}).mappings().all()
        check("all 30 collection_state rows exist", len(states) == 30, str(len(states)))

        success_ids = {int(e["soldier_id"]) for e in events if e["result"] == "success"}
        failure_ids = set(SOLDIER_IDS) - success_ids
        residual_ids = {int(j["soldier_id"]) for j in jobs}
        check("residual jobs correspond exactly to first-attempt failures",
              residual_ids == failure_ids, f"residual={sorted(residual_ids)} failures={sorted(failure_ids)}")

        row_counts = dict(conn.execute(text("""
            SELECT soldier_id, count(*) AS n
            FROM soldier_weapon_stats
            WHERE soldier_id=ANY(:ids)
            GROUP BY soldier_id
        """), {"ids": list(SOLDIER_IDS)}).all())
        check("successful soldiers persisted weapon rows",
              all(int(row_counts.get(sid, 0)) > 0 for sid in success_ids))
        check("failed soldiers persisted no weapon rows",
              all(int(row_counts.get(sid, 0)) == 0 for sid in failure_ids))

    print("\n===== PHYSICAL ATTEMPTS =====")
    for e in starts:
        print(
            f"soldier={e['soldier_id']} platform={e['platform']} "
            f"job={e['job_id']} attempt={e['attempt_number']} "
            f"collector={e['collector_uuid']}"
        )

    print("\n===== EVENTS =====")
    for e in events:
        meta = e["metadata"] or {}
        print(
            f"soldier={e['soldier_id']} platform={e['platform']} result={e['result']} "
            f"http={e['http_status']} duration_ms={e['duration_ms']} "
            f"bytes={meta.get('response_bytes')} rows={meta.get('weapon_rows')} "
            f"error={e['error_class']} collector={e['collector_uuid']}"
        )

    durations = [int(e["duration_ms"]) for e in events if e["duration_ms"] is not None]
    sizes = [int((e["metadata"] or {}).get("response_bytes")) for e in events
             if (e["metadata"] or {}).get("response_bytes") is not None]
    successes = sum(e["result"] == "success" for e in events)
    failures = len(events) - successes
    print("\n===== COST SUMMARY =====")
    print(f"successes={successes} failures={failures}")
    if durations:
        print(f"duration_ms mean={mean(durations):.1f} median={median(durations):.1f} min={min(durations)} max={max(durations)}")
    if sizes:
        print(f"response_bytes total={sum(sizes)} mean={mean(sizes):.1f} median={median(sizes):.1f} min={min(sizes)} max={max(sizes)}")
    print(f"residual retry jobs={len(jobs)}")
    print("\nPHASE 5A STAGE A POST-RUN AUDIT: PASS")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
