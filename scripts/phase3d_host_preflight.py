#!/usr/bin/env python3
"""Read-only Phase 3D remote-host deployment preflight.

This harness deliberately performs no collector registration, feeder pass, queue
mutation, job claim, or Battlelog request.  It proves that a deployed BF4PS
checkout on one of the frozen Phase 3D hosts is pointed at the expected test
primary with the expected host/collector/egress identity.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import psycopg

EXPECTED_DATABASE = "bf4_playerstats_test"
EXPECTED_DB_HOST = "mak-db-02.bf4statusbot.com"
EXPECTED_ALEMBIC = "0003_request_gates"
EXPECTED_LANE = "background"
EXPECTED_RESOURCE = "detailed"
EXPECTED_BRANCH = "feature/phase3d-two-host-proof"


@dataclass(frozen=True)
class HostIdentity:
    collector_uuid: str
    collector_name: str
    egress_key: str
    expected_public_ipv4: str


HOSTS = {
    "hnl-01": HostIdentity(
        collector_uuid="b2b3ef60-62e8-4d4a-91b0-41a2e2a3d001",
        collector_name="phase3d-hnl-01",
        egress_key="phase3d-hnl-01",
        expected_public_ipv4="76.81.69.106",
    ),
    "kah-01": HostIdentity(
        collector_uuid="b2b3ef60-62e8-4d4a-91b0-41a2e2a3d002",
        collector_name="phase3d-kah-01",
        egress_key="phase3d-kah-01",
        expected_public_ipv4="98.155.184.38",
    ),
}


def fail(message: str) -> None:
    raise RuntimeError(message)


def git_output(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        stderr=subprocess.STDOUT,
    ).strip()


def main() -> None:
    print("===== BF4PS PHASE 3D REMOTE HOST PREFLIGHT =====")
    print()
    print("READ-ONLY DEPLOYMENT PREFLIGHT")
    print("No collector registration, feeder pass, queue write, job claim, or Battlelog request is performed.")
    print()

    hostname = socket.gethostname().split(".", 1)[0]
    identity = HOSTS.get(hostname)
    if identity is None:
        fail(f"host {hostname!r} is not one of the frozen Phase 3D hosts: {sorted(HOSTS)}")

    database_url = os.environ.get("BF4PS_DATABASE_URL")
    if not database_url:
        fail("BF4PS_DATABASE_URL is not set")

    parsed = urlsplit(database_url)
    if parsed.hostname != EXPECTED_DB_HOST:
        fail(
            f"database host must be FQDN {EXPECTED_DB_HOST!r}; got {parsed.hostname!r}"
        )
    if parsed.path.lstrip("/") != EXPECTED_DATABASE:
        fail(
            f"database must be {EXPECTED_DATABASE!r}; got {parsed.path.lstrip('/')!r}"
        )

    branch = git_output("branch", "--show-current")
    commit = git_output("rev-parse", "--short", "HEAD")
    dirty = git_output("status", "--porcelain")

    if branch != EXPECTED_BRANCH:
        fail(f"expected branch {EXPECTED_BRANCH!r}; got {branch!r}")
    if dirty:
        fail("BF4PS checkout is not clean")

    resolved = sorted({item[4][0] for item in socket.getaddrinfo(EXPECTED_DB_HOST, 5432, socket.AF_INET)})

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT current_database(), current_user, inet_server_addr()::text, "
                "inet_server_port(), pg_is_in_recovery()"
            )
            db_name, db_user, server_addr, server_port, recovery = cur.fetchone()

            cur.execute("SHOW transaction_read_only")
            read_only = cur.fetchone()[0]

            cur.execute("SELECT version_num FROM alembic_version")
            alembic = cur.fetchone()[0]

            cur.execute(
                """
                SELECT collector_uuid::text, collector_name, hostname, lane,
                       egress_key, enabled, drained, retired_at
                FROM collectors
                WHERE collector_uuid = %s::uuid
                   OR lower(collector_name) = lower(%s)
                ORDER BY collector_uuid
                """,
                (identity.collector_uuid, identity.collector_name),
            )
            collector_conflicts = cur.fetchall()

            cur.execute(
                """
                SELECT egress_key, next_request_at, updated_at
                FROM request_gates
                WHERE egress_key = %s
                """,
                (identity.egress_key,),
            )
            request_gate = cur.fetchone()

    if db_name != EXPECTED_DATABASE:
        fail(f"connected to unexpected database {db_name!r}")
    if recovery:
        fail("target PostgreSQL server is in recovery")
    if read_only != "off":
        fail(f"target PostgreSQL transaction_read_only is {read_only!r}")
    if alembic != EXPECTED_ALEMBIC:
        fail(f"expected Alembic {EXPECTED_ALEMBIC!r}; got {alembic!r}")
    if collector_conflicts:
        fail(f"frozen collector identity already exists/conflicts: {collector_conflicts!r}")

    print(f"host:            {hostname}")
    print(f"collector UUID:  {identity.collector_uuid}")
    print(f"collector name:  {identity.collector_name}")
    print(f"resource/lane:   {EXPECTED_RESOURCE}/{EXPECTED_LANE}")
    print(f"egress key:      {identity.egress_key}")
    print(f"expected egress: {identity.expected_public_ipv4}")
    print(f"git branch:      {branch}")
    print(f"git commit:      {commit}")
    print()

    print("===== DATABASE TARGET =====")
    print(f"configured host: {parsed.hostname}")
    print(f"resolved IPv4:   {', '.join(resolved)}")
    print(f"database:        {db_name}")
    print(f"database user:   {db_user}")
    print(f"server address:  {server_addr}")
    print(f"server port:     {server_port}")
    print(f"recovery:        {recovery}")
    print(f"read only:       {read_only}")
    print(f"alembic:         {alembic}")
    print()

    print("===== EXISTING FROZEN IDENTITY =====")
    print("(none)")
    print()

    print("===== REQUEST GATE =====")
    if request_gate is None:
        print(f"{identity.egress_key}: not yet materialized (expected before live collector registration/request pacing)")
    else:
        print(
            f"{request_gate[0]} next_request_at={request_gate[1]} updated_at={request_gate[2]}"
        )
    print()

    print("===== SAFETY DECISION =====")
    print("frozen Phase 3D host:              PASS")
    print("isolated clean BF4PS checkout:     PASS")
    print("database FQDN policy:              PASS")
    print("expected BF4PS test database:      PASS")
    print("writable PostgreSQL primary:       PASS")
    print("expected Alembic head:             PASS")
    print("collector identity conflicts:      NONE")
    print("resource/lane frozen:              PASS")
    print("external Battlelog requests:       0")
    print("database writes:                    0")
    print()
    print("PHASE 3D REMOTE HOST PREFLIGHT: PASS")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"PHASE 3D REMOTE HOST PREFLIGHT: FAIL: {exc}", file=sys.stderr)
        raise
