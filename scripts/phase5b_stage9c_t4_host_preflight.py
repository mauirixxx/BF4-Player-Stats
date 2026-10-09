#!/usr/bin/env python3
"""T4 cross-host participant identity preflight (strictly read-only; no test race).

Runs only with explicit --check. Does not seed data, claim jobs, or contact Battlelog.
"""
from __future__ import annotations

import argparse
import os
import socket

from sqlalchemy import create_engine, text

from scripts.phase5b_stage9c_postgres_integration import (
    EXPECTED_DATABASE, EXPECTED_IP, EXPECTED_USER, refuse_unsafe_target,
)

HOSTS = {"tcou", "hnl-01", "kah-01"}
TABLES = ("collectors", "soldiers", "collection_jobs",
          "collection_events", "stage9c_supervision_runs")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="perform only read-only identity and empty-scratch checks")
    parser.add_argument("--expected-host", choices=sorted(HOSTS), required=True)
    args = parser.parse_args()
    if not args.check:
        parser.error("--check is required; no writes are implemented")
    actual = socket.gethostname().split(".")[0].lower()
    if actual != args.expected_host:
        raise RuntimeError(f"REFUSING unexpected hostname {actual!r} != {args.expected_host!r}")
    url = os.environ.get("BF4PS_STAGE9C_INTEGRATION_URL", "")
    if not url:
        parser.error("BF4PS_STAGE9C_INTEGRATION_URL required")
    refuse_unsafe_target(url)
    engine = create_engine(
        url, pool_pre_ping=True,
        connect_args={"connect_timeout": 5, "options": "-c statement_timeout=15000"},
    )
    try:
        with engine.connect() as conn:
            identity = conn.execute(text("""
                SELECT current_database(),current_user,inet_server_addr(),
                       pg_is_in_recovery(),current_setting('transaction_read_only'),
                       current_setting('transaction_isolation')
            """)).one()
            expected = (EXPECTED_DATABASE, EXPECTED_USER, EXPECTED_IP,
                        False, "off", "read committed")
            observed = (identity[0], identity[1], str(identity[2]),
                        identity[3], identity[4], identity[5])
            if observed != expected:
                raise RuntimeError(f"REFUSING scratch database identity: {observed}")
            revision = conn.execute(text(
                "SELECT version_num FROM public.alembic_version"
            )).scalar_one()
            if revision != "0004_stage9c_supervision_runs":
                raise RuntimeError(f"REFUSING unexpected Alembic head {revision}")
            for table in TABLES:
                n = conn.execute(text(
                    f"SELECT count(*) FROM public.{table}"
                )).scalar_one()
                if n:
                    raise RuntimeError(f"REFUSING nonempty scratch table {table}: {n}")
            conn.rollback()
        print(f"PASS: {actual} verified scratch primary, Alembic head and empty fixture tables")
        print("READ ONLY: zero SQL writes, zero HTTP collection, zero service changes")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
