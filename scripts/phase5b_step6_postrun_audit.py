#!/usr/bin/env python3
"""Read-only reconciliation for Phase 5B Step 6 bounded live run."""
from __future__ import annotations
import os
from urllib.parse import urlsplit
from sqlalchemy import create_engine, text
from bf4ps.phase5b_step6_cohort import (
    EXPECTED_DATABASE, EXPECTED_REVISION, GLOBAL_ATTEMPT_CEILING, HOSTS,
    RESOURCES, RUN_MARKER_EVENT_TYPE, RUN_NUMBER, SOLDIER_IDS,
)

def main() -> int:
    url=os.environ.get("BF4PS_DATABASE_URL"); parsed=urlsplit(url or "")
    if not url or parsed.path.lstrip("/") != EXPECTED_DATABASE:
        raise SystemExit("REFUSING: wrong or missing BF4PS_DATABASE_URL")
    engine=create_engine(url,pool_pre_ping=True)
    with engine.connect() as conn:
        db=conn.execute(text("SELECT current_database()")).scalar_one()
        rev=conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        if db != EXPECTED_DATABASE or rev != EXPECTED_REVISION:
            raise RuntimeError(f"wrong target db={db!r} revision={rev!r}")
        markers=conn.execute(text("""
          SELECT event_id FROM collection_events
          WHERE event_type=:t AND metadata->>'run_number'=:n ORDER BY event_id
        """),{"t":RUN_MARKER_EVENT_TYPE,"n":str(RUN_NUMBER)}).scalars().all()
        if len(markers)!=1: raise RuntimeError(f"expected one run marker; found {len(markers)}")
        boundary=int(markers[0])
        params={"b":boundary,"ids":list(SOLDIER_IDS),"resources":list(RESOURCES)}
        attempts=conn.execute(text("""
          SELECT job_id,attempt_number,MIN(occurred_at) occurred_at,
                 MIN(resource) resource,MIN(platform) platform,
                 MIN(collector_name_snapshot) collector,
                 MIN(egress_key_snapshot) egress
          FROM collection_events
          WHERE event_id>:b AND soldier_id=ANY(:ids) AND resource=ANY(:resources)
            AND lane='background' AND event_type='collection_attempt_started'
          GROUP BY job_id,attempt_number ORDER BY job_id,attempt_number
        """),params).mappings().all()
        terminals=conn.execute(text("""
          SELECT job_id,attempt_number,event_type,result,http_status,error_class
          FROM collection_events
          WHERE event_id>:b AND soldier_id=ANY(:ids) AND resource=ANY(:resources)
            AND lane='background' AND event_type IN ('collection_success','collection_failure')
          ORDER BY job_id,attempt_number,event_id
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
        foreign_starts=int(conn.execute(text("""
          SELECT COUNT(*) FROM collection_events WHERE event_id>:b
            AND event_type='collection_attempt_started' AND lane='background'
            AND NOT (soldier_id=ANY(:ids) AND resource=ANY(:resources))
            AND collector_name_snapshot=ANY(:names)
        """),{**params,"names":[h.collector_name for h in HOSTS.values()]}).scalar_one())
        remaining=conn.execute(text("""
          SELECT soldier_id,resource,status,attempt_count,last_error_class,last_error_at,eligible_at
          FROM collection_jobs WHERE soldier_id=ANY(:ids) AND resource=ANY(:resources)
          ORDER BY soldier_id,resource
        """),params).mappings().all()
        states=conn.execute(text("""
          SELECT soldier_id,
            detailed_state,detailed_last_success_at,detailed_next_due_at,detailed_consecutive_failures,
            weapons_state,weapons_last_success_at,weapons_next_due_at,weapons_consecutive_failures,
            vehicles_state,vehicles_last_success_at,vehicles_next_due_at,vehicles_consecutive_failures
          FROM collection_state WHERE soldier_id=ANY(:ids) ORDER BY soldier_id
        """),params).mappings().all()
        by_resource=conn.execute(text("""
          SELECT resource,COUNT(*) n FROM collection_events WHERE event_id>:b
            AND soldier_id=ANY(:ids) AND resource=ANY(:resources)
            AND event_type='collection_attempt_started' GROUP BY resource ORDER BY resource
        """),params).all()
        by_platform=conn.execute(text("""
          SELECT platform,COUNT(*) n FROM collection_events WHERE event_id>:b
            AND soldier_id=ANY(:ids) AND resource=ANY(:resources)
            AND event_type='collection_attempt_started' GROUP BY platform ORDER BY platform
        """),params).all()
        by_collector=conn.execute(text("""
          SELECT collector_name_snapshot,COUNT(*) n FROM collection_events WHERE event_id>:b
            AND soldier_id=ANY(:ids) AND resource=ANY(:resources)
            AND event_type='collection_attempt_started'
          GROUP BY collector_name_snapshot ORDER BY collector_name_snapshot
        """),params).all()
    engine.dispose()

    attempt_keys={(r["job_id"],r["attempt_number"]) for r in attempts}
    terminal_keys={(r["job_id"],r["attempt_number"]) for r in terminals}
    success=sum(1 for r in terminals if r["event_type"]=="collection_success")
    failure=sum(1 for r in terminals if r["event_type"]=="collection_failure")
    print("===== BF4PS PHASE 5B STEP 6 POST-RUN AUDIT =====")
    print(f"run_marker_event_id={boundary}")
    print(f"physical_attempts={len(attempts)} ceiling={GLOBAL_ATTEMPT_CEILING}")
    print(f"terminal_events={len(terminals)} success={success} failure={failure}")
    print(f"attempts_without_terminal={len(attempt_keys-terminal_keys)} terminals_without_start={len(terminal_keys-attempt_keys)}")
    print("by_resource=" + ",".join(f"{k}:{v}" for k,v in by_resource))
    print("by_platform=" + ",".join(f"{k}:{v}" for k,v in by_platform))
    print("by_collector=" + ",".join(f"{k}:{v}" for k,v in by_collector))
    print(f"403_429_or_throttle={throttle}")
    print(f"persistence_failures={persistence}")
    print(f"foreign_physical_starts_by_step6_collectors={foreign_starts}")
    print(f"remaining_cohort_jobs={len(remaining)}")
    for row in remaining: print("  REMAINING " + " ".join(f"{k}={v}" for k,v in row.items()))
    bad_states=[]
    for row in states:
        for resource in RESOURCES:
            if row[f"{resource}_state"]!="success" or int(row[f"{resource}_consecutive_failures"])!=0:
                bad_states.append((row["soldier_id"],resource,row[f"{resource}_state"],row[f"{resource}_consecutive_failures"]))
    print(f"non_success_or_failure_debt_states={len(bad_states)}")
    for item in bad_states: print(f"  STATE soldier={item[0]} resource={item[1]} state={item[2]} failures={item[3]}")
    due_bad=[]
    for row in states:
        for resource,hours in (("detailed",24),("weapons",168),("vehicles",168)):
            success_at=row[f"{resource}_last_success_at"]; due=row[f"{resource}_next_due_at"]
            if success_at is None or due is None or int((due-success_at).total_seconds()) != hours*3600:
                due_bad.append((row["soldier_id"],resource,success_at,due))
    print(f"due_interval_mismatches={len(due_bad)}")
    for item in due_bad: print(f"  DUE soldier={item[0]} resource={item[1]} success={item[2]} due={item[3]}")

    ok=(len(attempts)==GLOBAL_ATTEMPT_CEILING and len(terminals)==len(attempts)
        and not (attempt_keys-terminal_keys) and not (terminal_keys-attempt_keys)
        and failure==0 and throttle==0 and persistence==0 and foreign_starts==0
        and len(remaining)==0 and len(states)==len(SOLDIER_IDS)
        and not bad_states and not due_bad
        and dict(by_resource)=={r:9 for r in RESOURCES}
        and dict(by_platform)=={"pc":9,"ps4":9,"xboxone":9}
        and set(dict(by_collector))=={h.collector_name for h in HOSTS.values()})
    print("database writes: 0")
    print("Battlelog requests by audit: 0")
    print("PHASE 5B STEP 6 POST-RUN AUDIT: " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1

if __name__=="__main__":
    raise SystemExit(main())
