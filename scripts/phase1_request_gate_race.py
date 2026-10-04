"""Live PostgreSQL validation of BF4PS outbound request-gate serialization."""
from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import create_engine, text

from bf4ps.request_gate import reserve_request_slot

EGRESS_KEY = "phase1-live-request-gate-test"
INTERVAL_SECONDS = 2.0
CONTENDERS = 5


def main() -> None:
    database_url = os.environ.get("BF4PS_DATABASE_URL")
    if not database_url:
        raise SystemExit("BF4PS_DATABASE_URL is required")

    engine = create_engine(database_url)

    with engine.begin() as conn:
        database_name = conn.execute(text("SELECT current_database()")) .scalar_one()
        recovery = conn.execute(text("SELECT pg_is_in_recovery()")) .scalar_one()
        if "test" not in database_name.lower():
            raise SystemExit(f"REFUSING: not a test database: {database_name}")
        conn.execute(
            text("DELETE FROM request_gates WHERE egress_key = :egress_key"),
            {"egress_key": EGRESS_KEY},
        )

    print("===== BF4PS REQUEST GATE RACE =====\n")
    print(f"database:       {database_name}")
    print(f"recovery:       {recovery}")
    print(f"egress_key:     {EGRESS_KEY}")
    print(f"interval:       {INTERVAL_SECONDS:.3f}s")
    print(f"contenders:     {CONTENDERS}\n")

    barrier = threading.Barrier(CONTENDERS)

    def contender(number: int) -> dict[str, object]:
        with engine.begin() as conn:
            barrier.wait()
            permit = reserve_request_slot(
                conn,
                egress_key=EGRESS_KEY,
                interval_seconds=INTERVAL_SECONDS,
            )
        return {
            "contender": number,
            "reserved_at": permit.reserved_at,
            "wait_seconds": permit.wait_seconds,
            "next_request_at": permit.next_request_at,
        }

    with ThreadPoolExecutor(max_workers=CONTENDERS) as pool:
        results = list(pool.map(contender, range(1, CONTENDERS + 1)))

    results.sort(key=lambda row: row["reserved_at"])

    print("===== RESERVED SLOTS =====")
    previous = None
    deltas: list[float] = []
    for position, row in enumerate(results, start=1):
        reserved = row["reserved_at"]
        if previous is None:
            delta_text = "first"
        else:
            delta = (reserved - previous).total_seconds()
            deltas.append(delta)
            delta_text = f"{delta:.6f}s"
        print(
            f"slot {position}: contender={row['contender']} "
            f"reserved={reserved.isoformat()} delta={delta_text} "
            f"reported_wait={row['wait_seconds']:.6f}s"
        )
        previous = reserved

    print("\n===== VALIDATION =====")
    if len({row["reserved_at"] for row in results}) != CONTENDERS:
        raise AssertionError("duplicate request slots were assigned")

    tolerance = 0.001
    for delta in deltas:
        if delta < INTERVAL_SECONDS - tolerance:
            raise AssertionError(
                f"spacing violation: {delta:.6f}s < {INTERVAL_SECONDS:.6f}s"
            )

    print("unique slots:        PASS")
    print("minimum spacing:     PASS")

    with engine.connect() as conn:
        gate = conn.execute(
            text("""
                SELECT egress_key, next_request_at, updated_at
                FROM request_gates
                WHERE egress_key = :egress_key
            """),
            {"egress_key": EGRESS_KEY},
        ).mappings().one()

    expected_next = results[-1]["next_request_at"]
    print(f"final next slot:     {gate['next_request_at'].isoformat()}")
    if gate["next_request_at"] != expected_next:
        raise AssertionError(
            "database next_request_at does not match the final reservation"
        )
    print("final gate state:    PASS")

    with engine.begin() as conn:
        deleted = conn.execute(
            text("DELETE FROM request_gates WHERE egress_key = :egress_key"),
            {"egress_key": EGRESS_KEY},
        ).rowcount

    print(f"cleanup rows:        {deleted}")
    if deleted != 1:
        raise AssertionError("expected exactly one request gate row during cleanup")

    print("\nBF4PS REQUEST GATE RACE: PASS")


if __name__ == "__main__":
    main()
