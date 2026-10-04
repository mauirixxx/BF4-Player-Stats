"""Live PostgreSQL validation for the Phase 2 bounded detailed feeder.

This harness performs database queue writes only.  It does not invoke the
collector and cannot issue Battlelog requests.
"""
from __future__ import annotations

import os

from sqlalchemy import create_engine, text

from bf4ps.bounded_feeder import replenish_detailed_bootstrap

TARGET = 3
REASON = "bootstrap"


def actionable(conn):
    return int(conn.execute(text("""
        SELECT count(*)
        FROM collection_jobs
        WHERE resource='detailed'
          AND lane='background'
          AND status IN ('pending','claimed','running')
    """)).scalar_one())


def main():
    url = os.environ.get("BF4PS_DATABASE_URL")
    if not url:
        raise SystemExit("BF4PS_DATABASE_URL is required")
    engine = create_engine(url)

    print("===== BF4PS PHASE 2 BOUNDED FEEDER INTEGRATION =====")
    print()

    with engine.begin() as conn:
        db = conn.execute(text("SELECT current_database()" )).scalar_one()
        recovery = conn.execute(text("SELECT pg_is_in_recovery()" )).scalar_one()
        print(f"database: {db}")
        print(f"recovery: {recovery}")
        if "test" not in db.lower():
            raise SystemExit(f"REFUSING TO RUN against non-test database: {db}")
        if recovery:
            raise SystemExit("REFUSING TO RUN against a recovery/replica database")

        # Find a deterministic contiguous boundary containing at least TARGET
        # never-attempted supported soldiers.  Existing actionable jobs are
        # excluded because they must remain authoritative and untouched.
        candidates = conn.execute(text("""
            SELECT s.soldier_id, s.platform, s.persona_id, s.current_name
            FROM soldiers AS s
            JOIN collection_state AS cs USING (soldier_id)
            WHERE s.platform IN ('pc','ps4','xboxone')
              AND cs.detailed_state='never_attempted'
              AND NOT EXISTS (
                    SELECT 1 FROM collection_jobs AS j
                    WHERE j.soldier_id=s.soldier_id
                      AND j.resource='detailed'
              )
            ORDER BY s.soldier_id
            LIMIT :n
        """), {"n": TARGET}).mappings().all()

        if len(candidates) < TARGET:
            raise SystemExit(f"Need at least {TARGET} eligible never-attempted soldiers; found {len(candidates)}")

        max_soldier_id = int(candidates[-1]["soldier_id"])
        print(f"target depth:    {TARGET}")
        print(f"max soldier_id:  {max_soldier_id}")
        print("eligible sample:")
        for row in candidates:
            print(f"  {row['soldier_id']:>7}  {row['platform']:<8} persona={row['persona_id']!s:<12} {row['current_name']!r}")

        before_ids = set(conn.execute(text("""
            SELECT job_id FROM collection_jobs
            WHERE resource='detailed' AND lane='background'
        """)).scalars())
        before_depth = actionable(conn)

        # A pre-existing background detailed queue deeper than our tiny test
        # target would make this harness unable to prove the target invariant
        # without deleting legitimate work.  Refuse instead.
        if before_depth > TARGET:
            raise SystemExit(
                f"REFUSING: existing actionable detailed/background depth {before_depth} exceeds test target {TARGET}"
            )

        first = replenish_detailed_bootstrap(
            conn, target_depth=TARGET, max_soldier_id=max_soldier_id
        )
        second = replenish_detailed_bootstrap(
            conn, target_depth=TARGET, max_soldier_id=max_soldier_id
        )

        after_ids = set(conn.execute(text("""
            SELECT job_id FROM collection_jobs
            WHERE resource='detailed' AND lane='background'
        """)).scalars())
        created_ids = sorted(after_ids - before_ids)
        rows = conn.execute(text("""
            SELECT job_id, soldier_id, resource, lane, priority_class, reason, status
            FROM collection_jobs
            WHERE job_id = ANY(:ids)
            ORDER BY soldier_id
        """), {"ids": created_ids}).mappings().all() if created_ids else []

        print()
        print("===== FEEDER PASSES =====")
        print(f"first:  before={first.actionable_before} deficit={first.deficit} created={first.created} after={first.actionable_after}")
        print(f"second: before={second.actionable_before} deficit={second.deficit} created={second.created} after={second.actionable_after}")
        print()
        print("created queue rows:")
        for row in rows:
            print(f"  job={row['job_id']} soldier={row['soldier_id']} {row['resource']}/{row['lane']} {row['priority_class']} reason={row['reason']} status={row['status']}")

        assert first.actionable_after == TARGET
        assert second.actionable_before == TARGET
        assert second.created == 0
        assert second.actionable_after == TARGET
        assert len(created_ids) == first.created
        assert all(r["resource"] == "detailed" for r in rows)
        assert all(r["lane"] == "background" for r in rows)
        assert all(r["priority_class"] == "bootstrap" for r in rows)
        assert all(r["reason"] == REASON for r in rows)
        assert all(r["status"] == "pending" for r in rows)

        # Leave the test database exactly as we found it.  Only rows proven to
        # have been created by this transaction are removed.
        if created_ids:
            deleted = conn.execute(text("""
                DELETE FROM collection_jobs
                WHERE job_id = ANY(:ids)
                RETURNING job_id
            """), {"ids": created_ids}).scalars().all()
            assert set(deleted) == set(created_ids)

        final_ids = set(conn.execute(text("""
            SELECT job_id FROM collection_jobs
            WHERE resource='detailed' AND lane='background'
        """)).scalars())
        assert final_ids == before_ids

    print()
    print("===== VALIDATION =====")
    print("bounded target depth: PASS")
    print("repeat pass idempotent: PASS")
    print("bootstrap queue shape: PASS")
    print("existing queue preserved: PASS")
    print("cleanup: PASS")
    print("external requests: 0 (harness has no collector/Battlelog path)")
    print()
    print("BF4PS PHASE 2 BOUNDED FEEDER INTEGRATION: PASS")


if __name__ == "__main__":
    main()
