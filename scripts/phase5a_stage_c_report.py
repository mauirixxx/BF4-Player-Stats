#!/usr/bin/env python3
"""Read-only Phase 5A Stage C combined cost characterization."""
from __future__ import annotations

from collections import Counter
from statistics import mean, median
from sqlalchemy import text

from bf4ps.db import make_engine
from phase5a_stage_a_common import SOLDIER_IDS, assert_target
from phase5a_stage_a_common import current_run_start_event_id as stage_a_boundary
from phase5a_stage_b_common import current_run_start_event_id as stage_b_boundary

RESOURCES = (("weapons", stage_a_boundary), ("vehicles", stage_b_boundary))


def main() -> int:
    failures: list[str] = []
    def check(label: str, ok: bool, detail: str="") -> None:
        print(f"{label:<72} {'PASS' if ok else 'FAIL'}" + (f"  {detail}" if detail else ""))
        if not ok: failures.append(f"{label}: {detail or 'condition false'}")

    print("===== BF4PS PHASE 5A STAGE C COMBINED COST REPORT =====")
    print("database writes: 0")
    print("Battlelog requests: 0")
    engine=make_engine()
    summaries={}
    with engine.connect() as conn:
        assert_target(conn)
        for resource,boundary_fn in RESOURCES:
            boundary=boundary_fn(conn)
            starts=conn.execute(text("""
                SELECT soldier_id,platform,collector_uuid,job_id,attempt_number
                FROM collection_events
                WHERE resource=:resource AND lane='background'
                  AND soldier_id=ANY(:ids) AND event_id>:boundary
                  AND event_type='collection_attempt_started'
                ORDER BY event_id
            """),{"resource":resource,"ids":list(SOLDIER_IDS),"boundary":boundary}).mappings().all()
            events=conn.execute(text("""
                SELECT soldier_id,platform,result,http_status,duration_ms,error_class,metadata,
                       job_id,attempt_number
                FROM collection_events
                WHERE resource=:resource AND lane='background'
                  AND soldier_id=ANY(:ids) AND event_id>:boundary
                  AND event_type IN ('collection_success','collection_failure')
                ORDER BY event_id
            """),{"resource":resource,"ids":list(SOLDIER_IDS),"boundary":boundary}).mappings().all()
            pf=int(conn.execute(text("""
                SELECT count(*) FROM collection_events
                WHERE resource=:resource AND lane='background'
                  AND soldier_id=ANY(:ids) AND event_id>:boundary
                  AND event_type='collection_persistence_failure'
            """),{"resource":resource,"ids":list(SOLDIER_IDS),"boundary":boundary}).scalar_one())
            sizes=[int((e["metadata"] or {}).get("response_bytes")) for e in events
                   if (e["metadata"] or {}).get("response_bytes") is not None]
            durations=[int(e["duration_ms"]) for e in events if e["duration_ms"] is not None]
            summaries[resource]=dict(boundary=boundary,starts=starts,events=events,pf=pf,sizes=sizes,durations=durations)

        states=conn.execute(text("""
            SELECT soldier_id,detailed_state,weapons_state,vehicles_state
            FROM collection_state WHERE soldier_id=ANY(:ids)
        """),{"ids":list(SOLDIER_IDS)}).mappings().all()
        weapon_rows=dict(conn.execute(text("""
            SELECT soldier_id,count(*) FROM soldier_weapon_stats
            WHERE soldier_id=ANY(:ids) GROUP BY soldier_id
        """),{"ids":list(SOLDIER_IDS)}).all())
        vehicle_rows=dict(conn.execute(text("""
            SELECT soldier_id,count(*) FROM soldier_vehicle_stats
            WHERE soldier_id=ANY(:ids) GROUP BY soldier_id
        """),{"ids":list(SOLDIER_IDS)}).all())
        weapon_catalog=int(conn.execute(text("SELECT count(*) FROM weapon_catalog")).scalar_one())
        vehicle_catalog=int(conn.execute(text("SELECT count(*) FROM vehicle_catalog")).scalar_one())
        residual=int(conn.execute(text("""
            SELECT count(*) FROM collection_jobs
            WHERE soldier_id=ANY(:ids) AND resource IN ('weapons','vehicles')
        """),{"ids":list(SOLDIER_IDS)}).scalar_one())

    for resource in ("weapons","vehicles"):
        s=summaries[resource]
        starts=s["starts"]; events=s["events"]
        success=sum(e["result"]=="success" for e in events)
        temporary=sum(e["result"]!="success" for e in events)
        check(f"{resource}: exactly 30 measured physical requests",len(starts)==30,str(len(starts)))
        check(f"{resource}: exactly 30 terminal outcomes",len(events)==30,str(len(events)))
        check(f"{resource}: 30 successful outcomes",success==30,f"success={success} failure={temporary}")
        check(f"{resource}: platform split 10/10/10",Counter(e["platform"] for e in events)==Counter({"pc":10,"ps4":10,"xboxone":10}))
        check(f"{resource}: no throttle evidence",not any(e["http_status"] in {403,429} or e["error_class"]=="battlelog_throttle" for e in events))
        check(f"{resource}: no persistence failures",s["pf"]==0,str(s["pf"]))

    check("all 30 retain successful detailed state",len(states)==30 and all(r["detailed_state"]=="success" for r in states))
    check("all 30 weapon states are success",all(r["weapons_state"]=="success" for r in states))
    check("all 30 vehicle states are success",all(r["vehicles_state"]=="success" for r in states))
    check("zero residual weapon/vehicle jobs",residual==0,str(residual))

    w=summaries["weapons"]; v=summaries["vehicles"]
    measured_requests=len(w["starts"])+len(v["starts"])
    measured_bytes=sum(w["sizes"])+sum(v["sizes"])
    completed=30
    print("\n===== RESOURCE COST =====")
    for resource,s in summaries.items():
        print(f"{resource}: boundary={s['boundary']} requests={len(s['starts'])} terminal={len(s['events'])}")
        print(f"  bytes total={sum(s['sizes'])} mean={mean(s['sizes']):.1f} median={median(s['sizes']):.1f} min={min(s['sizes'])} max={max(s['sizes'])}")
        print(f"  duration_ms mean={mean(s['durations']):.1f} median={median(s['durations']):.1f} min={min(s['durations'])} max={max(s['durations'])}")

    print("\n===== ROW AMPLIFICATION =====")
    print(f"weapon rows total={sum(int(x) for x in weapon_rows.values())} per_soldier mean={mean(int(x) for x in weapon_rows.values()):.1f} min={min(weapon_rows.values())} max={max(weapon_rows.values())}")
    print(f"vehicle rows total={sum(int(x) for x in vehicle_rows.values())} per_soldier mean={mean(int(x) for x in vehicle_rows.values()):.1f} min={min(vehicle_rows.values())} max={max(vehicle_rows.values())}")
    print(f"current weapon_catalog rows={weapon_catalog}")
    print(f"current vehicle_catalog rows={vehicle_catalog}")
    print("catalog growth: NOT DERIVABLE — no authoritative pre-run catalog cardinality was frozen")

    print("\n===== COMBINED MEASURED PHASE 5A COST =====")
    print(f"completed soldiers={completed}")
    print(f"measured weapon+vehicle requests={measured_requests}")
    print(f"measured requests per completed soldier={measured_requests/completed:.1f}")
    print(f"measured weapon+vehicle bytes={measured_bytes}")
    print(f"measured weapon+vehicle bytes per completed soldier={measured_bytes/completed:.1f}")
    print(f"measured weapon+vehicle MiB per completed soldier={measured_bytes/completed/1024/1024:.3f}")
    print("production retained-stat resource shape: detailed + weapons + vehicles = 3 requests per soldier")
    print("Phase 5A measured only weapons + vehicles; detailed was a successful cohort precondition")
    print("do not add reconnaissance detailed payload estimates to measured Phase 5A byte totals")
    print("elapsed wall-clock: NOT DERIVED from summed request durations; use run/harness wall-clock evidence if needed")

    if failures:
        print(f"\nPHASE 5A STAGE C COMBINED COST REPORT: FAIL ({len(failures)} check(s))")
        for f in failures: print(" - "+f)
        return 1
    print("\nPHASE 5A STAGE C COMBINED COST REPORT: PASS")
    return 0

if __name__=="__main__": raise SystemExit(main())
