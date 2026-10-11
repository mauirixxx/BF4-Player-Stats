"""Three-site D2 synthetic claim worker: dry-run by default, never HTTP.

The execute mode is intentionally locked pending coordinator integration and
explicit authorization for cross-host scratch writes.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
from dataclasses import dataclass
from uuid import UUID, uuid5, NAMESPACE_URL

from sqlalchemy import create_engine, text

from scripts.phase5b_stage9c_d2_ledger_integration import (
    EXPECTED_DB, EXPECTED_IP, EXPECTED_USER, HEAD, validate_target,
)

ALLOWED_HOSTS = frozenset({"tcou", "kah-01", "hnl-01"})
MAX_WORKERS_PER_HOST = 32


@dataclass(frozen=True)
class WorkerConfig:
    host: str
    worker_index: int
    workers_on_host: int
    run_id: str
    collector_uuid: UUID

    @classmethod
    def build(cls, *, host: str, worker_index: int, workers_on_host: int, run_id: str):
        if host not in ALLOWED_HOSTS:
            raise ValueError("host not in approved three-site cohort")
        if not 1 <= workers_on_host <= MAX_WORKERS_PER_HOST:
            raise ValueError("workers-on-host must be 1..32")
        if not 0 <= worker_index < workers_on_host:
            raise ValueError("worker-index outside configured worker range")
        if not run_id or len(run_id) > 80 or not all(
            char.isascii() and (char.isalnum() or char in "-_") for char in run_id
        ):
            raise ValueError("run-id must contain 1..80 ASCII letters, numbers, hyphens or underscores")
        identity = uuid5(NAMESPACE_URL, f"bf4ps-d2-three-site:{run_id}:{host}:{worker_index}")
        return cls(host, worker_index, workers_on_host, run_id, identity)

    def report(self):
        return {
            "host": self.host,
            "worker_index": self.worker_index,
            "workers_on_host": self.workers_on_host,
            "run_id": self.run_id,
            "collector_uuid": str(self.collector_uuid),
            "mode": "dry-run",
            "http_requests": 0,
            "database_writes": 0,
        }


def check_database_identity(url: str) -> None:
    """Read-only, D2-locked identity check; no credentials are printed."""
    validate_target(url)
    engine = create_engine(url, connect_args={"connect_timeout": 5})
    try:
        with engine.connect() as conn:
            row = conn.execute(text(
                "SELECT current_database(),current_user,inet_server_addr(),"
                "pg_is_in_recovery(),current_setting('transaction_read_only')"
            )).one()
            if (row[0], row[1], str(row[2]), row[3], row[4]) != (
                EXPECTED_DB, EXPECTED_USER, EXPECTED_IP, False, "off"
            ):
                raise RuntimeError("REFUSING unexpected D2 identity")
            if conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() != HEAD:
                raise RuntimeError("REFUSING unexpected migration")
            conn.rollback()
    finally:
        engine.dispose()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--worker-index", required=True, type=int)
    parser.add_argument("--workers-on-host", required=True, type=int)
    parser.add_argument("--preflight-db", action="store_true",
                        help="read-only D2 identity check; requires BF4PS_STAGE9C_D2_URL")
    parser.add_argument("--execute", action="store_true",
                        help="reserved: unavailable until coordinator and safety review")
    args = parser.parse_args(argv)
    if args.execute:
        parser.error("cross-site scratch writes remain locked pending coordinator and approval")
    host = socket.gethostname().split(".")[0].lower()
    try:
        cfg = WorkerConfig.build(
            host=host, worker_index=args.worker_index,
            workers_on_host=args.workers_on_host, run_id=args.run_id)
        if args.preflight_db:
            url = os.environ.get("BF4PS_STAGE9C_D2_URL")
            if not url:
                parser.error("BF4PS_STAGE9C_D2_URL is required for D2 preflight")
            check_database_identity(url)
        report = cfg.report()
        report["d2_preflight"] = "pass" if args.preflight_db else "not_requested"
        print(json.dumps(report, sort_keys=True))
    except (ValueError, RuntimeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
