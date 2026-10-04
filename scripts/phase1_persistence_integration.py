"""Live PostgreSQL validation for the Phase 1 detailed-success transaction."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import create_engine, text

from bf4ps.battlelog_detailed import DECIMAL_FIELDS, INTEGER_FIELDS
from bf4ps.collection_jobs import claim_next_job, enqueue_job, mark_job_running
from bf4ps.detailed_persistence import persist_detailed_success

REASON = "phase1_persistence_integration"


def sample_stats(seed: int = 0):
    stats = {name: seed + i + 1 for i, name in enumerate(INTEGER_FIELDS)}
    for i, name in enumerate(DECIMAL_FIELDS):
        stats[name] = Decimal(seed + i + 1) / Decimal("10")
    return stats


def register_collector(conn, collector_uuid, name):
    conn.execute(text("""
        INSERT INTO collectors
            (collector_uuid, collector_name, hostname, lane, egress_key,
             enabled, drained, heartbeat_state)
        VALUES
            (:uuid, :name, 'tcou', 'background', :name, true, false, 'healthy')
    """), {"uuid": collector_uuid, "name": name})


def claim_running(engine, soldier_id, collector_uuid):
    with engine.begin() as conn:
        job_id = enqueue_job(conn, soldier_id=soldier_id, resource="detailed",
                             lane="background", priority_class="bootstrap",
                             reason=REASON)
    with engine.begin() as conn:
        job = claim_next_job(conn, collector_uuid=collector_uuid,
                             resource="detailed", lane="background",
                             lease_seconds=120)
        assert job is not None and job.job_id == job_id
        assert mark_job_running(conn, job)
        return job


def counts(conn, soldier_id):
    return {
        "current": conn.execute(text("SELECT count(*) FROM detailed_stats_current WHERE soldier_id=:s"), {"s": soldier_id}).scalar_one(),
        "history": conn.execute(text("SELECT count(*) FROM detailed_stats_history WHERE soldier_id=:s"), {"s": soldier_id}).scalar_one(),
        "events": conn.execute(text("SELECT count(*) FROM collection_events WHERE soldier_id=:s AND event_type='collection_success'"), {"s": soldier_id}).scalar_one(),
        "jobs": conn.execute(text("SELECT count(*) FROM collection_jobs WHERE soldier_id=:s AND resource='detailed'"), {"s": soldier_id}).scalar_one(),
    }


def main():
    url = os.environ.get("BF4PS_DATABASE_URL")
    if not url:
        raise SystemExit("BF4PS_DATABASE_URL is required")
    engine = create_engine(url)
    collector = uuid4()
    stale_collector = uuid4()

    with engine.begin() as conn:
        db = conn.execute(text("SELECT current_database()" )).scalar_one()
        if "test" not in db.lower():
            raise SystemExit(f"REFUSING TO RUN against non-test database: {db}")
        soldier = conn.execute(text("""
            SELECT soldier_id, persona_id, platform, current_name
            FROM soldiers ORDER BY soldier_id LIMIT 1
        """)).mappings().one()
        sid = soldier["soldier_id"]
        existing = conn.execute(text("""
            SELECT
              (SELECT count(*) FROM detailed_stats_current WHERE soldier_id=:s) +
              (SELECT count(*) FROM detailed_stats_history WHERE soldier_id=:s) +
              (SELECT count(*) FROM collection_jobs WHERE soldier_id=:s) +
              (SELECT count(*) FROM collection_events WHERE soldier_id=:s)
        """), {"s": sid}).scalar_one()
        if existing:
            raise SystemExit(f"REFUSING: soldier {sid} already has collection/stat rows")
        register_collector(conn, collector, "phase1-persist-main")
        register_collector(conn, stale_collector, "phase1-persist-stale")

    print("===== BF4PS PHASE 1 PERSISTENCE INTEGRATION =====")
    print(f"database:   {db}")
    print(f"soldier:    {soldier['current_name']} ({soldier['persona_id']}, {soldier['platform']})")

    t1 = datetime.now(timezone.utc)
    stats1 = sample_stats()
    job1 = claim_running(engine, sid, collector)
    with engine.begin() as conn:
        changed = persist_detailed_success(conn, job=job1, stats=stats1,
            source_fetched_at=t1, persona_id=soldier["persona_id"],
            platform=soldier["platform"], collector_name="phase1-persist-main",
            hostname="tcou", egress_key="phase1-persist-main", duration_ms=10)
        assert changed is True
    with engine.connect() as conn:
        c = counts(conn, sid)
        assert c == {"current": 1, "history": 1, "events": 1, "jobs": 0}, c
    print("first success:              PASS (current=1 history=1 event=1 job=0)")

    job2 = claim_running(engine, sid, collector)
    with engine.begin() as conn:
        changed = persist_detailed_success(conn, job=job2, stats=stats1,
            source_fetched_at=t1 + timedelta(seconds=1), persona_id=soldier["persona_id"],
            platform=soldier["platform"], collector_name="phase1-persist-main",
            hostname="tcou", egress_key="phase1-persist-main", duration_ms=11)
        assert changed is False
    with engine.connect() as conn:
        c = counts(conn, sid)
        assert c == {"current": 1, "history": 1, "events": 2, "jobs": 0}, c
    print("identical success:          PASS (history unchanged)")

    stats2 = dict(stats1)
    stats2["kills"] += 1
    job3 = claim_running(engine, sid, collector)
    with engine.begin() as conn:
        changed = persist_detailed_success(conn, job=job3, stats=stats2,
            source_fetched_at=t1 + timedelta(seconds=2), persona_id=soldier["persona_id"],
            platform=soldier["platform"], collector_name="phase1-persist-main",
            hostname="tcou", egress_key="phase1-persist-main", duration_ms=12)
        assert changed is True
    with engine.connect() as conn:
        c = counts(conn, sid)
        assert c == {"current": 1, "history": 2, "events": 3, "jobs": 0}, c
        state = conn.execute(text("SELECT detailed_state, detailed_consecutive_failures FROM collection_state WHERE soldier_id=:s"), {"s": sid}).one()
        assert state == ("success", 0), state
    print("changed success:            PASS (history appended)")
    print("collection state:           PASS")

    stale_job = claim_running(engine, sid, stale_collector)
    before = None
    with engine.connect() as conn:
        before = counts(conn, sid)
    with engine.begin() as conn:
        conn.execute(text("UPDATE collection_jobs SET lease_expires_at=now()-interval '1 second' WHERE job_id=:j"), {"j": stale_job.job_id})
    rejected = False
    try:
        with engine.begin() as conn:
            persist_detailed_success(conn, job=stale_job, stats=stats2,
                source_fetched_at=t1 + timedelta(seconds=3), persona_id=soldier["persona_id"],
                platform=soldier["platform"], collector_name="phase1-persist-stale",
                hostname="tcou", egress_key="phase1-persist-stale", duration_ms=13)
    except RuntimeError:
        rejected = True
    assert rejected
    with engine.connect() as conn:
        after = counts(conn, sid)
        assert after["current"] == before["current"]
        assert after["history"] == before["history"]
        assert after["events"] == before["events"]
        assert after["jobs"] == 1
    print("expired lease rejection:    PASS (no success writes committed)")

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM collection_jobs WHERE soldier_id=:s AND reason=:r"), {"s": sid, "r": REASON})
        conn.execute(text("DELETE FROM collection_events WHERE soldier_id=:s AND collector_uuid IN (:a,:b)"), {"s": sid, "a": collector, "b": stale_collector})
        conn.execute(text("DELETE FROM detailed_stats_history WHERE soldier_id=:s"), {"s": sid})
        conn.execute(text("DELETE FROM detailed_stats_current WHERE soldier_id=:s"), {"s": sid})
        conn.execute(text("UPDATE collection_state SET detailed_state='never_attempted', detailed_last_attempt_at=NULL, detailed_last_success_at=NULL, detailed_next_due_at=NULL, detailed_consecutive_failures=0, detailed_last_error_class=NULL, detailed_last_error_message=NULL, updated_at=now() WHERE soldier_id=:s"), {"s": sid})
        conn.execute(text("DELETE FROM collectors WHERE collector_uuid IN (:a,:b)"), {"a": collector, "b": stale_collector})
    print("cleanup:                    PASS")
    print("\nPHASE 1 PERSISTENCE INTEGRATION: PASS")


if __name__ == "__main__":
    main()
