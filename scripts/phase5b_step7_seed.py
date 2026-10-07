#!/usr/bin/env python3
"""Transactional seed for Phase 5B Step 7 endurance."""
from __future__ import annotations
import os
from urllib.parse import urlsplit
from sqlalchemy import create_engine, text
from bf4ps.phase5b_step7_endurance import (
    COHORT_SIZE, EXPECTED_DATABASE, EXPECTED_REVISION, INITIAL_JOB_COUNT,
    JOB_REASON, PLATFORMS, PRIORITY_CLASS, PRIORITY_VALUE, RESOURCES,
    RUN_MARKER_EVENT_TYPE, RUN_NUMBER, SOLDIERS_PER_PLATFORM, STEP6_SOLDIER_IDS,
)

def main() -> int:
    url=os.environ.get("BF4PS_DATABASE_URL"); parsed=urlsplit(url or "")
    if not url or parsed.path.lstrip("/") != EXPECTED_DATABASE:
        raise SystemExit("REFUSING: wrong or missing BF4PS_DATABASE_URL")
    engine=create_engine(url,pool_pre_ping=True)
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('bf4ps:phase5b-step7-seed'))"))
        db=conn.execute(text("SELECT current_database()")).scalar_one()
        rev=conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        recovery=bool(conn.execute(text("SELECT pg_is_in_recovery()")).scalar_one())
        ro=conn.execute(text("SELECT current_setting('transaction_read_only')")).scalar_one()
        if db!=EXPECTED_DATABASE or rev!=EXPECTED_REVISION or recovery or ro!="off":
            raise RuntimeError(f"wrong target db={db!r} revision={rev!r} recovery={recovery} read_only={ro!r}")
        markers=int(conn.execute(text(
            "SELECT COUNT(*) FROM collection_events WHERE event_type=:event_type"
        ),{"event_type":RUN_MARKER_EVENT_TYPE}).scalar_one())
        if markers: raise RuntimeError(f"Step 7 run marker already exists: {markers}")
        bg=int(conn.execute(text("SELECT COUNT(*) FROM collection_jobs WHERE lane='background'")).scalar_one())
        if bg: raise RuntimeError(f"background queue is not empty: {bg}")
        selected={}
        for platform in PLATFORMS:
            rows=conn.execute(text("""
                SELECT s.soldier_id
                FROM soldiers s JOIN collection_state cs ON cs.soldier_id=s.soldier_id
                WHERE s.platform=:platform
                  AND s.soldier_id <> ALL(:excluded)
                  AND cs.detailed_state='never_attempted'
                  AND cs.weapons_state='never_attempted'
                  AND cs.vehicles_state='never_attempted'
                  AND NOT EXISTS (
                    SELECT 1 FROM collection_jobs j
                    WHERE j.soldier_id=s.soldier_id AND j.resource=ANY(:resources)
                  )
                ORDER BY s.soldier_id LIMIT :limit
                FOR UPDATE OF s,cs
            """),{"platform":platform,"excluded":list(STEP6_SOLDIER_IDS),
                  "resources":list(RESOURCES),"limit":SOLDIERS_PER_PLATFORM}).scalars().all()
            if len(rows)!=SOLDIERS_PER_PLATFORM:
                raise RuntimeError(f"insufficient {platform} candidates: {len(rows)}")
            selected[platform]=[int(x) for x in rows]
        ids=[x for p in PLATFORMS for x in selected[p]]
        if len(ids)!=COHORT_SIZE or len(set(ids))!=COHORT_SIZE:
            raise RuntimeError("Step 7 cohort size/uniqueness mismatch")
        marker=conn.execute(text("""
            INSERT INTO collection_events(event_type,result,metadata)
            VALUES (:event_type,'started',CAST(:metadata AS jsonb))
            RETURNING event_id
        """),{
            "event_type":RUN_MARKER_EVENT_TYPE,
            "metadata":__import__("json").dumps({
                "run_number":RUN_NUMBER,
                "cohort_soldier_ids":ids,
                "platform_counts":{p:len(selected[p]) for p in PLATFORMS},
                "resources":list(RESOURCES),
                "initial_job_count":INITIAL_JOB_COUNT,
                "global_attempt_ceiling":3888,
                "duration_seconds":10800,
            },separators=(",",":")),
        }).scalar_one()
        inserted=int(conn.execute(text("""
            INSERT INTO collection_jobs(
              soldier_id,resource,lane,priority_class,reason,status,priority_value,eligible_at
            )
            SELECT soldier_id,resource,'background',:priority_class,:reason,'pending',:priority_value,now()
            FROM unnest(CAST(:ids AS bigint[])) soldier_id
            CROSS JOIN unnest(CAST(:resources AS text[])) resource
            ON CONFLICT (soldier_id,resource) DO NOTHING
        """),{"ids":ids,"resources":list(RESOURCES),"priority_class":PRIORITY_CLASS,
              "reason":JOB_REASON,"priority_value":PRIORITY_VALUE}).rowcount)
        if inserted!=INITIAL_JOB_COUNT:
            raise RuntimeError(f"expected {INITIAL_JOB_COUNT} inserted jobs; got {inserted}")
        shape=conn.execute(text("""
            SELECT COUNT(*) total,
              COUNT(*) FILTER (WHERE lane='background' AND priority_class=:priority_class
                AND reason=:reason AND status='pending' AND attempt_count=0
                AND collector_uuid IS NULL AND lease_token IS NULL AND claimed_at IS NULL
                AND started_at IS NULL AND lease_expires_at IS NULL) good
            FROM collection_jobs WHERE soldier_id=ANY(:ids) AND resource=ANY(:resources)
        """),{"ids":ids,"resources":list(RESOURCES),"priority_class":PRIORITY_CLASS,"reason":JOB_REASON}).mappings().one()
        if int(shape["total"])!=INITIAL_JOB_COUNT or int(shape["good"])!=INITIAL_JOB_COUNT:
            raise RuntimeError(f"seeded queue shape mismatch: {dict(shape)}")
    engine.dispose()
    print("===== BF4PS PHASE 5B STEP 7 SEED =====")
    print(f"run_marker_event_id={marker}")
    for p in PLATFORMS: print(f"{p} soldiers={len(selected[p])} range={selected[p][0]}..{selected[p][-1]}")
    print(f"cohort={len(ids)} queue_jobs={inserted} expected={INITIAL_JOB_COUNT}")
    print("queue_shape=background/bootstrap/pending/attempt0/unowned")
    print("Battlelog requests: 0")
    print("PHASE 5B STEP 7 SEED: PASS")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
