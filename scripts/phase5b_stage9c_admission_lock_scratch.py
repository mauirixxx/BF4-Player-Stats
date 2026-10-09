#!/usr/bin/env python3
"""Stage 9C scratch-only two-connection admission-lock/usage boundary proof.

This is a *partial* concurrency proof, NOT a production queue-claim proof.
It tests the production advisory lock and production _usage() on independent
PostgreSQL connections, including visibility of a newly committed start.
No HTTP, migrations, collectors, jobs, or systemd. Uses only the allowlisted
disposable database and deletes exact harness-owned event fixtures.
"""
from __future__ import annotations

import argparse
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

from sqlalchemy import create_engine, text

from bf4ps.background_service import BACKGROUND_SLOTS_PER_HOUR, _usage
from scripts.phase5b_stage9c_abort_drain_scratch import check
from scripts.phase5b_stage9c_postgres_integration import refuse_unsafe_target

LOCK = "SELECT pg_advisory_xact_lock(hashtext('bf4ps:phase5b-background-service'))"


def run(url: str) -> None:
    refuse_unsafe_target(url)
    engine = create_engine(
        url, pool_size=3, max_overflow=0, pool_pre_ping=True,
        connect_args={"connect_timeout": 5, "options": "-c statement_timeout=15000"},
    )
    marker = str(uuid4())
    winner_locked, release_winner = Event(), Event()
    try:
        # Guard all persistent writes. This database is disposable, but never
        # erase or reinterpret somebody else's scratch evidence.
        with engine.connect() as conn:
            check(conn)
            for table in ("collection_events", "collection_jobs", "soldiers"):
                if conn.execute(text(f"SELECT count(*) FROM public.{table}")).scalar_one():
                    raise RuntimeError(f"REFUSING nonempty public.{table}")
            conn.rollback()
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO public.collection_events
                    (resource,lane,event_type,attempt_number,metadata)
                SELECT 'detailed','background','collection_attempt_started',1,
                       jsonb_build_object('stage9c_admission_marker',CAST(:marker AS text),
                                          'priority_class','active','retry',false)
                FROM generate_series(1, :n)
            """), {"marker": marker, "n": BACKGROUND_SLOTS_PER_HOUR - 1})

        def winner():
            with engine.begin() as conn:
                conn.execute(text(LOCK))
                assert _usage(conn).total == BACKGROUND_SLOTS_PER_HOUR - 1
                conn.execute(text("""
                    INSERT INTO public.collection_events
                        (resource,lane,event_type,attempt_number,metadata)
                    VALUES ('weapons','background','collection_attempt_started',1,
                            jsonb_build_object('stage9c_admission_marker',
                                               CAST(:marker AS text),
                                               'priority_class','active','retry',false))
                """), {"marker": marker})
                winner_locked.set()
                if not release_winner.wait(timeout=10):
                    raise TimeoutError("winner transaction barrier expired")
                assert _usage(conn).total == BACKGROUND_SLOTS_PER_HOUR

        def loser():
            if not winner_locked.wait(timeout=10):
                raise TimeoutError("winner never acquired advisory lock")
            with engine.begin() as conn:
                conn.execute(text(LOCK))  # must wait for winner COMMIT
                total = _usage(conn).total
                assert total == BACKGROUND_SLOTS_PER_HOUR, total
                return total

        with ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(winner)
            b = pool.submit(loser)
            if not winner_locked.wait(timeout=10):
                raise TimeoutError("winner did not reach lock barrier")
            # Winner remains open until this explicit release; loser cannot
            # inspect a stale usage count while winner owns the advisory lock.
            release_winner.set()
            a.result(timeout=20)
            assert b.result(timeout=20) == BACKGROUND_SLOTS_PER_HOUR

        with engine.connect() as conn:
            assert _usage(conn).total == BACKGROUND_SLOTS_PER_HOUR
            conn.rollback()
        print("PASS: independent PostgreSQL connections serialize shared admission lock")
        print("PASS: second transaction sees committed 1296th physical start")
        print("NOTE: actual queue claims, reservations and lease reclaim NOT yet proven")
    finally:
        release_winner.set()
        try:
            with engine.begin() as conn:
                # Exact marker only. Failure to clean is a hard failure.
                deleted = conn.execute(text("""
                    DELETE FROM public.collection_events
                    WHERE metadata->>'stage9c_admission_marker' = :marker
                """), {"marker": marker}).rowcount
            with engine.connect() as conn:
                remaining = conn.execute(text("""
                    SELECT count(*) FROM public.collection_events
                    WHERE metadata->>'stage9c_admission_marker' = :marker
                """), {"marker": marker}).scalar_one()
                conn.rollback()
            if remaining:
                raise RuntimeError(f"FAILED scratch cleanup: {remaining} rows")
            print(f"PASS: exact scratch fixture cleanup ({deleted} rows)")
        finally:
            engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    url = os.environ.get("BF4PS_STAGE9C_INTEGRATION_URL", "")
    if not url:
        parser.error("BF4PS_STAGE9C_INTEGRATION_URL required")
    refuse_unsafe_target(url)
    if not args.execute:
        print("DRY RUN: no SQL or writes; explicit --execute required")
        return
    run(url)


if __name__ == "__main__":
    main()
