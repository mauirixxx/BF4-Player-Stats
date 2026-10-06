"""Frozen contract/helpers for the Phase 4B 900-player sustained collection run."""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text

from phase4b_cohort import SOLDIER_IDS

EXPECTED_DATABASE = "bf4_playerstats_test"
EXPECTED_DB_HOST = "mak-db-02.bf4statusbot.com"
EXPECTED_REVISION = "0003_request_gates"
TARGET_DEPTH = 6
GLOBAL_ATTEMPT_CEILING = 900
REQUEST_INTERVAL_SECONDS = 5.0
LEASE_SECONDS = 120


@dataclass(frozen=True)
class FrozenHost:
    collector_uuid: UUID
    collector_name: str
    egress_key: str


HOSTS = {
    "hnl-01": FrozenHost(
        UUID("b2b3ef60-62e8-4d4a-91b0-41a2e2a3e001"),
        "phase3e-hnl-01",
        "phase3e-hnl-01",
    ),
    "kah-01": FrozenHost(
        UUID("b2b3ef60-62e8-4d4a-91b0-41a2e2a3e002"),
        "phase3e-kah-01",
        "phase3e-kah-01",
    ),
    "tcou": FrozenHost(
        UUID("b2b3ef60-62e8-4d4a-91b0-41a2e2a3e003"),
        "phase3e-tcou",
        "phase3e-tcou",
    ),
}
FROZEN_UUIDS = tuple(host.collector_uuid for host in HOSTS.values())

assert len(SOLDIER_IDS) == GLOBAL_ATTEMPT_CEILING
assert len(set(SOLDIER_IDS)) == GLOBAL_ATTEMPT_CEILING


def assert_target(conn) -> None:
    row = conn.execute(
        text(
            """
            SELECT current_database() AS database_name,
                   pg_is_in_recovery() AS recovery,
                   current_setting('transaction_read_only') AS read_only
            """
        )
    ).mappings().one()
    revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    if row["database_name"] != EXPECTED_DATABASE:
        raise RuntimeError(f"wrong database {row['database_name']!r}")
    if row["recovery"] or row["read_only"] != "off":
        raise RuntimeError("Phase 4B requires the writable test primary")
    if revision != EXPECTED_REVISION:
        raise RuntimeError(f"unexpected Alembic revision {revision!r}")


def terminal_attempts(conn) -> int:
    return int(
        conn.execute(
            text(
                """
                SELECT count(*)
                FROM collection_events
                WHERE resource = 'detailed'
                  AND lane = 'background'
                  AND soldier_id = ANY(:ids)
                  AND event_type IN ('collection_success','collection_failure')
                """
            ),
            {"ids": list(SOLDIER_IDS)},
        ).scalar_one()
    )
