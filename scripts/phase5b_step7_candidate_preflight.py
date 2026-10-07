#!/usr/bin/env python3
"""Read-only candidate census for Phase 5B Step 7 endurance."""
from __future__ import annotations
import os
from urllib.parse import urlsplit
from sqlalchemy import create_engine, text
from bf4ps.phase5b_step7_endurance import (
    EXPECTED_DATABASE, EXPECTED_REVISION, PLATFORMS, RESOURCES,
    SOLDIERS_PER_PLATFORM, STEP6_SOLDIER_IDS, RUN_MARKER_EVENT_TYPE,
)

def main() -> int:
    url=os.environ.get("BF4PS_DATABASE_URL"); parsed=urlsplit(url or "")
    if not url or parsed.path.lstrip("/") != EXPECTED_DATABASE:
        raise SystemExit("REFUSING: wrong or missing BF4PS_DATABASE_URL")
    engine=create_engine(url,pool_pre_ping=True)
    selected={}
    with engine.connect() as conn:
        db=conn.execute(text("SELECT current_database()")).scalar_one()
        rev=conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        recovery=bool(conn.execute(text("SELECT pg_is_in_recovery()")).scalar_one())
        ro=conn.execute(text("SELECT current_setting('transaction_read_only')")).scalar_one()
        if db!=EXPECTED_DATABASE or rev!=EXPECTED_REVISION or recovery or ro!="off":
            raise RuntimeError(f"wrong target db={db!r} revision={rev!r} recovery={recovery} read_only={ro!r}")
        markers=int(conn.execute(text(
            "SELECT COUNT(*) FROM collection_events WHERE event_type=:event_type"
        ),{"event_type":RUN_MARKER_EVENT_TYPE}).scalar_one())
        if markers:
            raise RuntimeError(f"Step 7 run marker already exists: {markers}")
        foreign_background=int(conn.execute(text(
            "SELECT COUNT(*) FROM collection_jobs WHERE lane='background'"
        )).scalar_one())
        if foreign_background:
            raise RuntimeError(f"background queue is not empty: {foreign_background} jobs")
        for platform in PLATFORMS:
            rows=conn.execute(text("""
                SELECT s.soldier_id
                FROM soldiers s
                JOIN collection_state cs ON cs.soldier_id=s.soldier_id
                WHERE s.platform=:platform
                  AND s.soldier_id <> ALL(:excluded)
                  AND cs.detailed_state='never_attempted'
                  AND cs.weapons_state='never_attempted'
                  AND cs.vehicles_state='never_attempted'
                  AND NOT EXISTS (
                    SELECT 1 FROM collection_jobs j
                    WHERE j.soldier_id=s.soldier_id
                      AND j.resource=ANY(:resources)
                  )
                ORDER BY s.soldier_id
                LIMIT :limit
            """),{"platform":platform,"excluded":list(STEP6_SOLDIER_IDS),
                  "resources":list(RESOURCES),"limit":SOLDIERS_PER_PLATFORM}).scalars().all()
            selected[platform]=[int(x) for x in rows]
            if len(rows)!=SOLDIERS_PER_PLATFORM:
                raise RuntimeError(
                    f"insufficient pristine {platform} candidates: "
                    f"{len(rows)} < {SOLDIERS_PER_PLATFORM}"
                )
    engine.dispose()
    ids=[x for p in PLATFORMS for x in selected[p]]
    if len(ids)!=len(set(ids)):
        raise RuntimeError("candidate selection contains duplicate soldier IDs")
    print("===== BF4PS PHASE 5B STEP 7 CANDIDATE PREFLIGHT =====")
    print(f"database={EXPECTED_DATABASE} revision={EXPECTED_REVISION} primary_writable=yes")
    print("candidate_rule=all retained resources never_attempted; no retained-resource queue work")
    for platform in PLATFORMS:
        values=selected[platform]
        print(f"{platform}: selected={len(values)} soldier_id_range={values[0]}..{values[-1]}")
    print(f"total_selected={len(ids)} initial_jobs={len(ids)*len(RESOURCES)}")
    print("background_queue_before_seed=0")
    print("Step 7 run markers=0")
    print("database writes: 0")
    print("Battlelog requests: 0")
    print("PHASE 5B STEP 7 CANDIDATE PREFLIGHT: PASS")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
