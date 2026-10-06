#!/usr/bin/env python3
"""Read-only preflight after Stage B probe reset and run boundary creation."""
from __future__ import annotations

from sqlalchemy import text

from bf4ps.db import make_engine
from bf4ps.phase5a_frozen_cohort import FROZEN_COHORT
from phase5a_stage_b_common import (
    FROZEN_UUIDS, GLOBAL_ATTEMPT_CEILING, HOSTS, RUN_NUMBER, SOLDIER_IDS,
    current_run_start_event_id, assert_target,
)


def main() -> int:
    failures: list[str] = []
    def check(label: str, ok: bool, detail: str="") -> None:
        print(f"{label:<70} {'PASS' if ok else 'FAIL'}" + (f"  {detail}" if detail else ""))
        if not ok: failures.append(f"{label}: {detail or 'condition false'}")

    print("===== BF4PS PHASE 5A STAGE B RUN #1 POST-RESET PREFLIGHT =====")
    print("database writes: 0")
    print("Battlelog requests: 0")
    engine = make_engine()
    with engine.connect() as conn:
        assert_target(conn)
        boundary = current_run_start_event_id(conn)

        rows = conn.execute(text("""
            SELECT s.soldier_id, s.persona_id, s.current_name, s.platform,
                   cs.detailed_state, cs.weapons_state, cs.vehicles_state,
                   cs.vehicles_last_attempt_at, cs.vehicles_last_success_at,
                   cs.vehicles_next_due_at, cs.vehicles_consecutive_failures,
                   cs.vehicles_last_error_class, cs.vehicles_last_error_message
            FROM soldiers s JOIN collection_state cs USING (soldier_id)
            WHERE s.soldier_id=ANY(:ids) ORDER BY s.soldier_id
        """), {"ids": list(SOLDIER_IDS)}).mappings().all()
        actual = {(r["soldier_id"], r["persona_id"], r["current_name"], r["platform"]) for r in rows}
        expected = {(int(a), int(b), str(c), str(d)) for a,b,c,d in FROZEN_COHORT}
        check("exact frozen 30 identities unchanged", actual == expected, f"rows={len(rows)}")
        check("platform split is 10/10/10", {p:sum(r["platform"]==p for r in rows) for p in ("pc","ps4","xboxone")} == {"pc":10,"ps4":10,"xboxone":10})
        check("all detailed states remain success", all(r["detailed_state"]=="success" for r in rows))
        check("all Stage A weapon states remain success", all(r["weapons_state"]=="success" for r in rows))
        pristine = all(
            r["vehicles_state"]=="never_attempted"
            and r["vehicles_last_attempt_at"] is None
            and r["vehicles_last_success_at"] is None
            and r["vehicles_next_due_at"] is None
            and int(r["vehicles_consecutive_failures"])==0
            and r["vehicles_last_error_class"] is None
            and r["vehicles_last_error_message"] is None
            for r in rows
        )
        check("all vehicle collection states are pristine", pristine)

        weapon_soldiers = int(conn.execute(text("""
            SELECT count(DISTINCT soldier_id) FROM soldier_weapon_stats WHERE soldier_id=ANY(:ids)
        """), {"ids": list(SOLDIER_IDS)}).scalar_one())
        vehicle_rows = int(conn.execute(text("""
            SELECT count(*) FROM soldier_vehicle_stats WHERE soldier_id=ANY(:ids)
        """), {"ids": list(SOLDIER_IDS)}).scalar_one())
        jobs = int(conn.execute(text("""
            SELECT count(*) FROM collection_jobs WHERE resource IN ('weapons','vehicles') OR lane='background'
        """)).scalar_one())
        current_events = int(conn.execute(text("""
            SELECT count(*) FROM collection_events
            WHERE resource='vehicles' AND soldier_id=ANY(:ids) AND event_id>:boundary
              AND event_type IN ('collection_attempt_started','collection_success',
                                'collection_failure','collection_persistence_failure')
        """), {"ids": list(SOLDIER_IDS), "boundary": boundary}).scalar_one())
        check("Stage A weapon persistence remains for all 30", weapon_soldiers==30, str(weapon_soldiers))
        check("current vehicle persistence is empty", vehicle_rows==0, str(vehicle_rows))
        check("weapon/vehicle/background queue is empty", jobs==0, str(jobs))
        check("no Stage B run attempts after boundary", current_events==0, str(current_events))

        collectors = conn.execute(text("""
            SELECT collector_uuid, collector_name, hostname, egress_key,
                   enabled, drained, current_job_id
            FROM collectors WHERE collector_uuid=ANY(:uuids)
        """), {"uuids": list(FROZEN_UUIDS)}).mappings().all()
        check("all three frozen collectors registered", len(collectors)==3, str(len(collectors)))
        expected_collectors = {
            (str(h.collector_uuid), h.collector_name, hostname, h.egress_key)
            for hostname,h in HOSTS.items()
        }
        actual_collectors = {
            (str(r["collector_uuid"]), r["collector_name"], r["hostname"], r["egress_key"])
            for r in collectors
        }
        check("collector identities match frozen contract", actual_collectors==expected_collectors)
        check("collectors enabled, undrained, idle", all(r["enabled"] and not r["drained"] and r["current_job_id"] is None for r in collectors))

        gates = int(conn.execute(text("""
            SELECT count(*) FROM request_gates WHERE egress_key=ANY(:keys)
        """), {"keys": [h.egress_key for h in HOSTS.values()]}).scalar_one())
        check("all three PostgreSQL request gates exist", gates==3, str(gates))

    print(f"Stage B Run #{RUN_NUMBER} boundary event_id={boundary}")
    if failures:
        print(f"PHASE 5A STAGE B RUN #1 POST-RESET PREFLIGHT: FAIL ({len(failures)})")
        for f in failures: print(" - "+f)
        return 1
    print("PHASE 5A STAGE B RUN #1 POST-RESET PREFLIGHT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
