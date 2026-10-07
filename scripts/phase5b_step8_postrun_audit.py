#!/usr/bin/env python3
"""Read-only Phase 5B Step 8 forensic reconciliation for the Step 7 endurance run."""
from __future__ import annotations
import os
from collections import Counter, defaultdict
from datetime import timedelta
from urllib.parse import urlsplit
from sqlalchemy import create_engine, text
from bf4ps.phase5b_step7_endurance import (
    EXPECTED_DATABASE, EXPECTED_REVISION, GLOBAL_ATTEMPT_CEILING, HOSTS,
    LIVE_START_EVENT_TYPE, RESOURCES, RUN_MARKER_EVENT_TYPE, RUN_NUMBER,
)

def main() -> int:
    url=os.environ.get("BF4PS_DATABASE_URL"); parsed=urlsplit(url or "")
    if not url or parsed.path.lstrip("/") != EXPECTED_DATABASE:
        raise SystemExit("REFUSING: wrong or missing BF4PS_DATABASE_URL")
    engine=create_engine(url,pool_pre_ping=True)
    with engine.connect() as conn:
        db=conn.execute(text("SELECT current_database()")).scalar_one()
        rev=conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        writable=not bool(conn.execute(text("SELECT pg_is_in_recovery()")).scalar_one())
        if db!=EXPECTED_DATABASE or rev!=EXPECTED_REVISION or not writable:
            raise RuntimeError(f"wrong target db={db!r} revision={rev!r} writable={writable}")

        markers=conn.execute(text("""
          SELECT event_id,occurred_at,metadata FROM collection_events
          WHERE event_type=:t AND metadata->>'run_number'=:n ORDER BY event_id
        """),{"t":RUN_MARKER_EVENT_TYPE,"n":str(RUN_NUMBER)}).mappings().all()
        lives=conn.execute(text("""
          SELECT event_id,occurred_at,metadata FROM collection_events
          WHERE event_type=:t AND metadata->>'run_number'=:n ORDER BY event_id
        """),{"t":LIVE_START_EVENT_TYPE,"n":str(RUN_NUMBER)}).mappings().all()
        if len(markers)!=1 or len(lives)!=1:
            raise RuntimeError(f"expected one run/live marker; found run={len(markers)} live={len(lives)}")
        marker,lives0=markers[0],lives[0]
        boundary=int(marker["event_id"]); live_id=int(lives0["event_id"])
        ids=tuple(int(x) for x in marker["metadata"]["cohort_soldier_ids"])
        if len(ids)!=1296 or len(set(ids))!=1296:
            raise RuntimeError(f"bad frozen cohort size/uniqueness: {len(ids)}/{len(set(ids))}")
        params={"b":boundary,"ids":list(ids),"resources":list(RESOURCES)}

        attempts=conn.execute(text("""
          SELECT event_id,occurred_at,job_id,attempt_number,resource,platform,
                 collector_name_snapshot collector,egress_key_snapshot egress
          FROM collection_events
          WHERE event_id>:b AND soldier_id=ANY(:ids) AND resource=ANY(:resources)
            AND lane='background' AND event_type='collection_attempt_started'
          ORDER BY occurred_at,event_id
        """),params).mappings().all()
        terminals=conn.execute(text("""
          SELECT event_id,occurred_at,job_id,attempt_number,event_type,result,
                 http_status,error_class,resource,platform,collector_name_snapshot collector
          FROM collection_events
          WHERE event_id>:b AND soldier_id=ANY(:ids) AND resource=ANY(:resources)
            AND lane='background' AND event_type IN ('collection_success','collection_failure')
          ORDER BY occurred_at,event_id
        """),params).mappings().all()
        persistence=int(conn.execute(text("""
          SELECT COUNT(*) FROM collection_events WHERE event_id>:b
            AND soldier_id=ANY(:ids) AND resource=ANY(:resources)
            AND event_type='collection_persistence_failure'
        """),params).scalar_one())
        throttle=int(conn.execute(text("""
          SELECT COUNT(*) FROM collection_events WHERE event_id>:b
            AND soldier_id=ANY(:ids) AND resource=ANY(:resources)
            AND (http_status IN (403,429) OR error_class='battlelog_throttle')
        """),params).scalar_one())
        foreign=int(conn.execute(text("""
          SELECT COUNT(*) FROM collection_events WHERE event_id>:b
            AND event_type='collection_attempt_started' AND lane='background'
            AND NOT (soldier_id=ANY(:ids) AND resource=ANY(:resources))
            AND collector_name_snapshot=ANY(:names)
        """),{**params,"names":[h.collector_name for h in HOSTS.values()]}).scalar_one())
        remaining=conn.execute(text("""
          SELECT soldier_id,resource,status,attempt_count,collector_uuid,lease_token,
                 claimed_at,started_at,lease_expires_at,last_error_class,last_error_at,eligible_at
          FROM collection_jobs WHERE soldier_id=ANY(:ids) AND resource=ANY(:resources)
          ORDER BY soldier_id,resource
        """),params).mappings().all()
        states=conn.execute(text("""
          SELECT soldier_id,
            detailed_state,detailed_last_attempt_at,detailed_last_success_at,detailed_next_due_at,detailed_consecutive_failures,
            weapons_state,weapons_last_attempt_at,weapons_last_success_at,weapons_next_due_at,weapons_consecutive_failures,
            vehicles_state,vehicles_last_attempt_at,vehicles_last_success_at,vehicles_next_due_at,vehicles_consecutive_failures
          FROM collection_state WHERE soldier_id=ANY(:ids) ORDER BY soldier_id
        """),params).mappings().all()
        collectors=conn.execute(text("""
          SELECT collector_name,hostname,egress_key,enabled,drained,heartbeat_state,
                 current_job_id,started_at,last_heartbeat_at
          FROM collectors WHERE collector_uuid=ANY(:uuids) ORDER BY collector_name
        """),{"uuids":[h.collector_uuid for h in HOSTS.values()]}).mappings().all()
    engine.dispose()

    akeys=[(r["job_id"],r["attempt_number"]) for r in attempts]
    tkeys=[(r["job_id"],r["attempt_number"]) for r in terminals]
    ac,tc=Counter(akeys),Counter(tkeys)
    duplicate_attempt_keys=sum(v-1 for v in ac.values() if v>1)
    duplicate_terminal_keys=sum(v-1 for v in tc.values() if v>1)
    missing_terminal=set(ac)-set(tc); orphan_terminal=set(tc)-set(ac)
    success=sum(r["event_type"]=="collection_success" for r in terminals)
    failure=sum(r["event_type"]=="collection_failure" for r in terminals)
    by_resource=Counter(r["resource"] for r in attempts)
    by_platform=Counter(r["platform"] for r in attempts)
    by_collector=Counter(r["collector"] for r in attempts)
    unique_jobs=len({r["job_id"] for r in attempts})
    retry_attempts=len(attempts)-unique_jobs

    per_job=defaultdict(list)
    for r in attempts: per_job[r["job_id"]].append(r)
    retry_gaps=[]
    for rows in per_job.values():
        rows.sort(key=lambda r:(r["attempt_number"],r["occurred_at"]))
        for prev,cur in zip(rows,rows[1:]):
            retry_gaps.append((cur["occurred_at"]-prev["occurred_at"]).total_seconds())
    retry_gap_min=min(retry_gaps) if retry_gaps else None

    # Exact rolling one-hour maximum across all physical starts.
    times=[r["occurred_at"] for r in attempts]
    left=0; rolling_max=0
    for right,t in enumerate(times):
        while left<=right and t-times[left]>=timedelta(hours=1): left+=1
        rolling_max=max(rolling_max,right-left+1)

    spacing_bad=[]
    by_egress=defaultdict(list)
    for r in attempts: by_egress[r["egress"]].append(r)
    for egress,rows in by_egress.items():
        rows.sort(key=lambda r:r["occurred_at"])
        for prev,cur in zip(rows,rows[1:]):
            gap=(cur["occurred_at"]-prev["occurred_at"]).total_seconds()
            if gap < 5.0:
                spacing_bad.append((egress,prev["event_id"],cur["event_id"],gap))

    bad_states=[]; due_bad=[]
    for row in states:
        for resource,hours in (("detailed",24),("weapons",168),("vehicles",168)):
            state=row[f"{resource}_state"]; failures=int(row[f"{resource}_consecutive_failures"])
            if state=="success":
                success_at=row[f"{resource}_last_success_at"]; due=row[f"{resource}_next_due_at"]
                if success_at is None or due is None or int((due-success_at).total_seconds())!=hours*3600:
                    due_bad.append((row["soldier_id"],resource,success_at,due))
            elif state=="temporary_failure":
                if failures<1: bad_states.append((row["soldier_id"],resource,state,failures))
            else:
                bad_states.append((row["soldier_id"],resource,state,failures))

    owned_remaining=[r for r in remaining if r["status"]!="pending" or r["collector_uuid"] is not None or r["lease_token"] is not None]
    print("===== BF4PS PHASE 5B STEP 8 POST-RUN FORENSIC AUDIT =====")
    print(f"run_marker_event_id={boundary} live_start_event_id={live_id}")
    print(f"live_started_at={lives0['occurred_at'].isoformat()}")
    print(f"physical_attempts={len(attempts)} ceiling={GLOBAL_ATTEMPT_CEILING} unique_jobs_attempted={unique_jobs} retry_attempts={retry_attempts}")
    print(f"terminal_events={len(terminals)} success={success} failure={failure}")
    print(f"duplicate_attempt_keys={duplicate_attempt_keys} duplicate_terminal_keys={duplicate_terminal_keys}")
    print(f"attempts_without_terminal={len(missing_terminal)} terminals_without_start={len(orphan_terminal)}")
    print("by_resource="+",".join(f"{k}:{by_resource[k]}" for k in sorted(by_resource)))
    print("by_platform="+",".join(f"{k}:{by_platform[k]}" for k in sorted(by_platform)))
    print("by_collector="+",".join(f"{k}:{by_collector[k]}" for k in sorted(by_collector)))
    print(f"rolling_1h_max_physical_starts={rolling_max} ceiling=1296")
    print(f"per_egress_spacing_violations_lt_5s={len(spacing_bad)}")
    for x in spacing_bad[:20]: print(f"  SPACING egress={x[0]} events={x[1]}->{x[2]} gap_seconds={x[3]:.6f}")
    print(f"retry_gap_min_seconds={retry_gap_min if retry_gap_min is not None else 'n/a'}")
    print(f"403_429_or_throttle={throttle} persistence_failures={persistence} foreign_physical_starts={foreign}")
    print(f"remaining_cohort_jobs={len(remaining)} owned_or_nonpending_remaining={len(owned_remaining)}")
    for r in remaining[:30]: print("  REMAINING "+" ".join(f"{k}={v}" for k,v in r.items()))
    print(f"collection_state_rows={len(states)} bad_state_rows={len(bad_states)} due_interval_mismatches={len(due_bad)}")
    for x in bad_states[:30]: print(f"  STATE soldier={x[0]} resource={x[1]} state={x[2]} failures={x[3]}")
    for x in due_bad[:30]: print(f"  DUE soldier={x[0]} resource={x[1]} success={x[2]} due={x[3]}")
    print("collectors:")
    for r in collectors: print("  "+" ".join(f"{k}={v}" for k,v in r.items()))

    ok=(len(attempts)==GLOBAL_ATTEMPT_CEILING and len(terminals)==len(attempts)
        and duplicate_attempt_keys==0 and duplicate_terminal_keys==0
        and not missing_terminal and not orphan_terminal
        and throttle==0 and persistence==0 and foreign==0
        and rolling_max<=1296 and not spacing_bad
        and len(states)==len(ids) and not bad_states and not due_bad
        and not owned_remaining
        and set(by_collector)=={h.collector_name for h in HOSTS.values()})
    print("database writes: 0")
    print("Battlelog requests by audit: 0")
    print("PHASE 5B STEP 8 POST-RUN FORENSIC AUDIT: "+("PASS" if ok else "FAIL"))
    return 0 if ok else 1

if __name__=="__main__":
    raise SystemExit(main())
