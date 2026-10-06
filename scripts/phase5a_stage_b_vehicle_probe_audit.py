#!/usr/bin/env python3
"""Read-only audit of the one-soldier Stage B vehicle lifecycle probe."""
from __future__ import annotations

from sqlalchemy import text

from bf4ps.db import make_engine
from phase5a_stage_a_common import assert_target

SOLDIER_ID = 15
PROBE_EVENT_TYPE = "phase5a_stage_b_vehicle_probe_started"


def main() -> int:
    failures: list[str] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        print(f"{label:<68} {'PASS' if ok else 'FAIL'}" + (f"  {detail}" if detail else ""))
        if not ok:
            failures.append(f"{label}: {detail or 'condition false'}")

    print("===== BF4PS PHASE 5A STAGE B VEHICLE PROBE AUDIT =====")
    print("database writes: 0")
    print("Battlelog requests: 0")

    engine = make_engine()
    with engine.connect() as conn:
        assert_target(conn)
        marker = conn.execute(text("""
            SELECT event_id FROM collection_events
            WHERE event_type=:event_type AND soldier_id=:soldier_id
            ORDER BY event_id DESC LIMIT 1
        """), {"event_type": PROBE_EVENT_TYPE, "soldier_id": SOLDIER_ID}).scalar_one()

        starts = conn.execute(text("""
            SELECT event_id, job_id, attempt_number, collector_uuid
            FROM collection_events
            WHERE resource='vehicles' AND soldier_id=:soldier_id
              AND event_type='collection_attempt_started' AND event_id>:marker
            ORDER BY event_id
        """), {"soldier_id": SOLDIER_ID, "marker": marker}).mappings().all()
        terminals = conn.execute(text("""
            SELECT event_id, job_id, attempt_number, result, http_status,
                   duration_ms, error_class, metadata, collector_uuid
            FROM collection_events
            WHERE resource='vehicles' AND soldier_id=:soldier_id
              AND event_type IN ('collection_success','collection_failure')
              AND event_id>:marker
            ORDER BY event_id
        """), {"soldier_id": SOLDIER_ID, "marker": marker}).mappings().all()
        persistence_failures = conn.execute(text("""
            SELECT event_id, error_class, error_message, metadata
            FROM collection_events
            WHERE resource='vehicles' AND soldier_id=:soldier_id
              AND event_type='collection_persistence_failure' AND event_id>:marker
            ORDER BY event_id
        """), {"soldier_id": SOLDIER_ID, "marker": marker}).mappings().all()

        state = conn.execute(text("""
            SELECT weapons_state, vehicles_state, vehicles_consecutive_failures,
                   vehicles_last_error_class, vehicles_last_error_message
            FROM collection_state WHERE soldier_id=:soldier_id
        """), {"soldier_id": SOLDIER_ID}).mappings().one()
        weapon_rows = int(conn.execute(text("""
            SELECT count(*) FROM soldier_weapon_stats WHERE soldier_id=:soldier_id
        """), {"soldier_id": SOLDIER_ID}).scalar_one())
        vehicle_rows = int(conn.execute(text("""
            SELECT count(*) FROM soldier_vehicle_stats WHERE soldier_id=:soldier_id
        """), {"soldier_id": SOLDIER_ID}).scalar_one())
        jobs = conn.execute(text("""
            SELECT job_id, status, attempt_count, last_error_class
            FROM collection_jobs WHERE soldier_id=:soldier_id AND resource='vehicles'
        """), {"soldier_id": SOLDIER_ID}).mappings().all()

    check("exactly one durable physical vehicle attempt", len(starts) == 1, str(len(starts)))
    check("exactly one terminal vehicle event", len(terminals) == 1, str(len(terminals)))
    if len(starts) == 1 and len(terminals) == 1:
        check(
            "physical attempt reconciles to terminal event",
            (starts[0]["job_id"], starts[0]["attempt_number"])
            == (terminals[0]["job_id"], terminals[0]["attempt_number"]),
        )
    check("no persistence failure evidence", not persistence_failures, str(persistence_failures))
    check("accepted Stage A weapon state remains success", state["weapons_state"] == "success", str(state["weapons_state"]))
    check("accepted Stage A weapon rows remain present", weapon_rows > 0, str(weapon_rows))

    success = len(terminals) == 1 and terminals[0]["result"] == "success"
    if success:
        meta = terminals[0]["metadata"] or {}
        check("terminal HTTP status is 200", terminals[0]["http_status"] == 200, str(terminals[0]["http_status"]))
        check("vehicle state is success", state["vehicles_state"] == "success", str(state["vehicles_state"]))
        check("vehicle persistence contains rows", vehicle_rows > 0, str(vehicle_rows))
        check("terminal vehicle_rows matches persistence", int(meta.get("vehicle_rows", -1)) == vehicle_rows,
              f"event={meta.get('vehicle_rows')} db={vehicle_rows}")
        check("successful job finalized from queue", not jobs, str(jobs))
    else:
        check("failed probe persisted no vehicle rows", vehicle_rows == 0, str(vehicle_rows))
        check("failed probe leaves one retry job", len(jobs) == 1, str(jobs))

    print(f"probe boundary event_id={marker}")
    print(f"vehicle_rows={vehicle_rows} weapon_rows={weapon_rows}")
    if terminals:
        e = terminals[0]
        print(
            f"terminal result={e['result']} http={e['http_status']} duration_ms={e['duration_ms']} "
            f"bytes={(e['metadata'] or {}).get('response_bytes')} "
            f"rows={(e['metadata'] or {}).get('vehicle_rows')} error={e['error_class']}"
        )

    if failures:
        print(f"PHASE 5A STAGE B VEHICLE PROBE AUDIT: FAIL ({len(failures)} check(s))")
        for failure in failures:
            print(f" - {failure}")
        return 1
    print("PHASE 5A STAGE B VEHICLE PROBE AUDIT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
