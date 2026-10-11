"""D2 lock-race probe: two independent PostgreSQL sessions, no HTTP.

Uses the exact transaction advisory lock employed by the physical-start
gate. Holds it in session A and proves session B cannot acquire it until
A rolls back. No database rows are created or modified.
"""
from sqlalchemy import text
from scripts.stage9c_three_site_live_ignition import engine
from scripts.stage9c_three_hour_soak_ledger import guard

LOCK = "SELECT pg_try_advisory_xact_lock(90841011,3)"


def main():
    e=engine()
    with e.connect() as a, e.connect() as b:
        ta=a.begin()
        tb=b.begin()
        try:
            guard(a)
            guard(b)
            pid_a=a.execute(text("SELECT pg_backend_pid()")).scalar_one()
            pid_b=b.execute(text("SELECT pg_backend_pid()")).scalar_one()
            if pid_a==pid_b:
                raise RuntimeError("not independent PostgreSQL backends")
            if not a.execute(text(LOCK)).scalar_one():
                raise RuntimeError("session A could not acquire lock")
            if b.execute(text(LOCK)).scalar_one():
                raise RuntimeError("session B bypassed active admission lock")
            ta.rollback()
            if not b.execute(text(LOCK)).scalar_one():
                raise RuntimeError("session B did not acquire released lock")
            print("LOCK RACE PASS separate_backends=2 second_blocked=true release_handoff=true")
        finally:
            if ta.is_active:
                ta.rollback()
            if tb.is_active:
                tb.rollback()


if __name__=="__main__":
    main()
