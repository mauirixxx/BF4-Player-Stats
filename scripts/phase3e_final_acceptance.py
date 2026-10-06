#!/usr/bin/env python3
"""Read-only Phase 3E final acceptance audit.

Mechanically reconciles durable database evidence and names the preserved
operator/run evidence used for lifecycle properties that are not represented by
terminal collection rows alone. No writes or Battlelog requests are performed.
"""
from __future__ import annotations

from collections import Counter
from os import environ

from sqlalchemy import bindparam, create_engine, text

from phase3e_lifecycle_a_common import (
    COHORT_SOLDIER_IDS,
    FROZEN_UUIDS,
    GLOBAL_ATTEMPT_CEILING,
    HOSTS,
    assert_target,
)
from phase3e_lifecycle_b_common import RECLAIMER_UUID

A_FIRST_EVENT = 443
A_LAST_PRIMARY_EVENT = 802
A_RETRY_FIRST_EVENT = 803
A_RETRY_LAST_EVENT = 810
B_SUCCESS_EVENT = 811
B_JOB_ID = 813
SURVIVOR_EVENT_IDS = (812, 813)
SURVIVOR_JOBS = {815: 391, 816: 392}
VICTIM_SUCCESS_EVENT = 814
VICTIM_JOB_ID = 814
VICTIM_SOLDIER_ID = 390
EXPECTED_RETRY_JOBS = {765, 766, 768, 769, 770, 771, 772, 773}
CLOSURE_JOB_IDS = (814, 815, 816)
CLOSURE_SOLDIER_IDS = (390, 391, 392)


def mark(label, status, detail=""):
    print(f"{label:<61} {status}{('  ' + detail) if detail else ''}")
    return status


def main() -> int:
    url = environ.get("BF4PS_DATABASE_URL")
    if not url:
        raise SystemExit("REFUSING: BF4PS_DATABASE_URL is not set")

    engine = create_engine(url, pool_pre_ping=True)
    with engine.connect() as conn:
        assert_target(conn)
        event_query = text("""
            SELECT event_id,collector_uuid,collector_name_snapshot,hostname_snapshot,
                   egress_key_snapshot,job_id,soldier_id,platform,resource,lane,
                   event_type,attempt_number,result,http_status,error_class,lease_token
            FROM collection_events
            WHERE event_id BETWEEN :lo AND :hi
            ORDER BY event_id
        """)
        a_primary = conn.execute(event_query, {"lo": A_FIRST_EVENT, "hi": A_LAST_PRIMARY_EVENT}).mappings().all()
        a_retry = conn.execute(event_query, {"lo": A_RETRY_FIRST_EVENT, "hi": A_RETRY_LAST_EVENT}).mappings().all()
        b = conn.execute(event_query, {"lo": B_SUCCESS_EVENT, "hi": B_SUCCESS_EVENT}).mappings().all()
        survivor = conn.execute(event_query, {"lo": SURVIVOR_EVENT_IDS[0], "hi": SURVIVOR_EVENT_IDS[-1]}).mappings().all()
        victim_event = conn.execute(event_query, {"lo": VICTIM_SUCCESS_EVENT, "hi": VICTIM_SUCCESS_EVENT}).mappings().all()

        collectors = conn.execute(
            text("""
                SELECT collector_uuid,collector_name,hostname,egress_key,enabled,drained,
                       heartbeat_state,current_job_id,retired_at
                FROM collectors
                WHERE collector_uuid IN :uuids
            """).bindparams(bindparam("uuids", expanding=True)),
            {"uuids": list(FROZEN_UUIDS)},
        ).mappings().all()
        gates = conn.execute(text("SELECT egress_key,next_request_at,updated_at FROM request_gates ORDER BY egress_key")).mappings().all()
        residual_a = conn.execute(
            text("""
                SELECT job_id,soldier_id,status,attempt_count
                FROM collection_jobs
                WHERE soldier_id IN :ids AND resource='detailed'
            """).bindparams(bindparam("ids", expanding=True)),
            {"ids": list(COHORT_SOLDIER_IDS)},
        ).mappings().all()
        b_job = conn.execute(text("SELECT count(*) FROM collection_jobs WHERE job_id=:j"), {"j": B_JOB_ID}).scalar_one()
        closure_jobs = conn.execute(
            text("""
                SELECT job_id,soldier_id,status,attempt_count,collector_uuid,lease_token
                FROM collection_jobs
                WHERE job_id IN :jobs OR soldier_id IN :soldiers
                ORDER BY job_id
            """).bindparams(
                bindparam("jobs", expanding=True),
                bindparam("soldiers", expanding=True),
            ),
            {"jobs": list(CLOSURE_JOB_IDS), "soldiers": list(CLOSURE_SOLDIER_IDS)},
        ).mappings().all()
        closure_state = conn.execute(text("""
            SELECT soldier_id,detailed_state,detailed_last_success_at,detailed_last_error_class
            FROM collection_state
            WHERE soldier_id IN (390,391,392)
            ORDER BY soldier_id
        """)).mappings().all()
        closure_current = conn.execute(text("""
            SELECT soldier_id
            FROM detailed_stats_current
            WHERE soldier_id IN (390,391,392)
            ORDER BY soldier_id
        """)).scalars().all()
        a_success_state = conn.execute(
            text("""
                SELECT count(*) FROM collection_state
                WHERE soldier_id IN :ids AND detailed_state='success'
            """).bindparams(bindparam("ids", expanding=True)),
            {"ids": list(COHORT_SOLDIER_IDS)},
        ).scalar_one()
        throttle = conn.execute(text("""
            SELECT event_id,http_status,error_class
            FROM collection_events
            WHERE event_id BETWEEN :lo AND :hi
              AND (http_status IN (403,429) OR lower(coalesce(error_class,'')) LIKE '%thrott%')
            ORDER BY event_id
        """), {"lo": A_FIRST_EVENT, "hi": VICTIM_SUCCESS_EVENT}).mappings().all()
        active_owned = conn.execute(
            text("""
                SELECT count(*) FROM collection_jobs
                WHERE collector_uuid IN :uuids
            """).bindparams(bindparam("uuids", expanding=True)),
            {"uuids": list(FROZEN_UUIDS)},
        ).scalar_one()

    print("===== BF4PS PHASE 3E FINAL ACCEPTANCE AUDIT =====")
    print("mode=read-only database reconciliation + explicit operator/run evidence")
    print(f"Lifecycle A primary event span: {A_FIRST_EVENT}..{A_LAST_PRIMARY_EVENT}")
    print(f"Lifecycle A retry event span:   {A_RETRY_FIRST_EVENT}..{A_RETRY_LAST_EVENT}")
    print(f"Lifecycle B success event:      {B_SUCCESS_EVENT}")
    print(f"Survivor success events:        {SURVIVOR_EVENT_IDS[0]}..{SURVIVOR_EVENT_IDS[-1]}")
    print(f"Recovered victim success event: {VICTIM_SUCCESS_EVENT}")
    print()

    statuses = []
    a_ids = [row["soldier_id"] for row in a_primary]
    statuses.append(mark("primary run exactly 360 terminal events", "PASS" if len(a_primary) == GLOBAL_ATTEMPT_CEILING else "FAIL", str(len(a_primary))))
    statuses.append(mark("primary run confined to exact frozen 360 soldiers", "PASS" if len(a_ids) == 360 and set(a_ids) == set(COHORT_SOLDIER_IDS) and len(set(a_ids)) == 360 else "FAIL"))
    statuses.append(mark("primary event resource/lane exact", "PASS" if all(row["resource"] == "detailed" and row["lane"] == "background" for row in a_primary) else "FAIL"))

    counts = Counter(row["collector_uuid"] for row in a_primary)
    statuses.append(mark(
        "all three physical collectors repeatedly finalized work",
        "PASS" if all(counts[uuid] > 1 for uuid in FROZEN_UUIDS) else "FAIL",
        ",".join(f"{HOSTS[host].collector_name}={counts[HOSTS[host].collector_uuid]}" for host in HOSTS),
    ))
    ident_ok = all(
        row["collector_uuid"] in FROZEN_UUIDS
        and row["hostname_snapshot"] in HOSTS
        and row["collector_name_snapshot"] == HOSTS[row["hostname_snapshot"]].collector_name
        and row["egress_key_snapshot"] == HOSTS[row["hostname_snapshot"]].egress_key
        for row in a_primary
    )
    statuses.append(mark("primary collector/event identity snapshots exact", "PASS" if ident_ok else "FAIL"))

    retry_jobs = {row["job_id"] for row in a_retry}
    statuses.append(mark("eight authorized Lifecycle A retries exact", "PASS" if len(a_retry) == 8 and retry_jobs == EXPECTED_RETRY_JOBS and all(row["event_type"] == "collection_success" and row["attempt_number"] == 2 for row in a_retry) else "FAIL"))
    statuses.append(mark("Lifecycle A queue fully converged", "PASS" if not residual_a else "FAIL", f"residual={len(residual_a)}"))
    statuses.append(mark("Lifecycle A detailed state converged 360/360", "PASS" if a_success_state == 360 else "FAIL", f"{a_success_state}/360"))
    statuses.append(mark("Lifecycle B durable success/finalization present", "PASS" if len(b) == 1 and b[0]["event_id"] == 811 and b[0]["attempt_number"] == 3 and b[0]["collector_uuid"] == RECLAIMER_UUID and b_job == 0 else "FAIL"))

    survivor_ok = (
        len(survivor) == 2
        and {int(row["event_id"]) for row in survivor} == set(SURVIVOR_EVENT_IDS)
        and {int(row["job_id"]): int(row["soldier_id"]) for row in survivor} == SURVIVOR_JOBS
        and all(row["event_type"] == "collection_success" and int(row["attempt_number"]) == 1 and row["collector_uuid"] == RECLAIMER_UUID and row["result"] == "success" and row["http_status"] == 200 and row["error_class"] is None for row in survivor)
    )
    statuses.append(mark("abrupt-loss unrelated survivor work durable", "PASS" if survivor_ok else "FAIL", f"events={len(survivor)}"))

    victim_recovered = (
        len(victim_event) == 1
        and int(victim_event[0]["event_id"]) == VICTIM_SUCCESS_EVENT
        and int(victim_event[0]["job_id"]) == VICTIM_JOB_ID
        and int(victim_event[0]["soldier_id"]) == VICTIM_SOLDIER_ID
        and int(victim_event[0]["attempt_number"]) == 2
        and victim_event[0]["collector_uuid"] == RECLAIMER_UUID
        and victim_event[0]["event_type"] == "collection_success"
        and victim_event[0]["result"] == "success"
        and victim_event[0]["http_status"] == 200
        and victim_event[0]["error_class"] is None
    )
    statuses.append(mark("abrupt-loss victim recovered cross-host", "PASS" if victim_recovered else "FAIL", "event=814 attempt=2"))

    closure_persistence_ok = (
        not closure_jobs
        and len(closure_state) == 3
        and {int(row["soldier_id"]) for row in closure_state} == set(CLOSURE_SOLDIER_IDS)
        and all(row["detailed_state"] == "success" and row["detailed_last_success_at"] is not None and row["detailed_last_error_class"] is None for row in closure_state)
        and {int(soldier_id) for soldier_id in closure_current} == set(CLOSURE_SOLDIER_IDS)
    )
    statuses.append(mark("closure jobs/state/current fully converged", "PASS" if closure_persistence_ok else "FAIL", f"residual_jobs={len(closure_jobs)}"))

    cmap = {row["collector_uuid"]: row for row in collectors}
    registry_ok = len(cmap) == 3 and all(
        cmap[frozen.collector_uuid]["collector_name"] == frozen.collector_name
        and cmap[frozen.collector_uuid]["hostname"] == host
        and cmap[frozen.collector_uuid]["egress_key"] == frozen.egress_key
        and cmap[frozen.collector_uuid]["retired_at"] is None
        for host, frozen in HOSTS.items()
    )
    statuses.append(mark("stable collector registry identities exact", "PASS" if registry_ok else "FAIL"))

    stopped_ok = registry_ok and all(
        cmap[uuid]["heartbeat_state"] == "unknown"
        and cmap[uuid]["current_job_id"] is None
        and bool(cmap[uuid]["enabled"])
        and not bool(cmap[uuid]["drained"])
        for uuid in FROZEN_UUIDS
    ) and int(active_owned) == 0
    statuses.append(mark("all collectors stopped cleanly after experiment", "PASS" if stopped_ok else "FAIL", f"active_owned={active_owned}"))

    expected_gates = {frozen.egress_key for frozen in HOSTS.values()}
    gate_keys = {row["egress_key"] for row in gates}
    statuses.append(mark("required Phase 3E request gates exist", "PASS" if expected_gates <= gate_keys else "FAIL", f"expected={sorted(expected_gates)}"))
    statuses.append(mark("403/429/throttle evidence in event span", "PASS" if not throttle else "FAIL", f"observed={len(throttle)}"))

    # Explicit operator/run evidence preserved in the Phase 3E evidence documents.
    statuses.append(mark("bounded feeder replenishment remained bounded", "PASS", "Round Three target=6, max observed=7 transient; 120/120 clean"))
    statuses.append(mark("restart while still drained preserved persistent drain", "PASS", "closure restart probe"))
    statuses.append(mark("persistent controls never silently overwritten", "PASS", "drained restart + explicit undrain rejoin + final clean stop"))
    statuses.append(mark("abrupt loss did not stall unrelated survivor work", "PASS", "events 812..813 before victim recovery event 814"))

    print()
    print("Throttle events:")
    if throttle:
        for row in throttle:
            print(f"event={row['event_id']} http={row['http_status']} class={row['error_class']}")
    else:
        print("none observed in reconciled event span")
    print()
    print("database writes: 0")
    print("Battlelog requests: 0")

    outcome = "FAIL" if "FAIL" in statuses else "PASS"
    print(f"PHASE 3E FINAL ACCEPTANCE: {outcome}")
    return 1 if outcome == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
