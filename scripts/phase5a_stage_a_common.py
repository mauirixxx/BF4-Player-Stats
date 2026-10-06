"""Shared boundaries for Phase 5A Stage A weapon characterization."""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text

from bf4ps.phase5a_frozen_cohort import FROZEN_COHORT

EXPECTED_DATABASE = "bf4_playerstats_test"
EXPECTED_REVISION = "0003_request_gates"
REQUEST_INTERVAL_SECONDS = 5.0
LEASE_SECONDS = 120
GLOBAL_ATTEMPT_CEILING = 30
RETRY_AFTER_SECONDS = 86400
SOFTWARE_VERSION = "phase5a-stage-a-weapons"
JOB_REASON = "phase5a_stage_a_weapons"
PRIORITY_VALUE = 1_000_000
RUN_MARKER_EVENT_TYPE = "phase5a_stage_a_run_started"
RUN_NUMBER = 2

SOLDIER_IDS = tuple(int(row[0]) for row in FROZEN_COHORT)

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

def assert_target(conn) -> None:
    db = conn.execute(text("SELECT current_database()")).scalar_one()
    revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    recovery = bool(conn.execute(text("SELECT pg_is_in_recovery()")).scalar_one())
    read_only = conn.execute(text("SELECT current_setting('transaction_read_only')")).scalar_one()
    if db != EXPECTED_DATABASE or revision != EXPECTED_REVISION or recovery or read_only != "off":
        raise RuntimeError(
            f"wrong target db={db!r} revision={revision!r} recovery={recovery} read_only={read_only!r}"
        )

def current_run_start_event_id(conn) -> int:
    row = conn.execute(text("""
        SELECT event_id
        FROM collection_events
        WHERE event_type=:event_type
          AND metadata->>'run_number'=:run_number
        ORDER BY event_id DESC
        LIMIT 1
    """), {"event_type": RUN_MARKER_EVENT_TYPE, "run_number": str(RUN_NUMBER)}).one_or_none()
    if row is None:
        raise RuntimeError(f"Phase 5A Stage A run {RUN_NUMBER} marker does not exist")
    return int(row.event_id)

def terminal_attempts(conn, *, after_event_id: int | None = None) -> int:
    boundary = "" if after_event_id is None else "AND event_id > :after_event_id"
    params = {"ids": list(SOLDIER_IDS)}
    if after_event_id is not None:
        params["after_event_id"] = after_event_id
    return int(conn.execute(text(f"""
        SELECT count(*)
        FROM collection_events
        WHERE resource='weapons'
          AND lane='background'
          AND soldier_id=ANY(:ids)
          AND event_type IN ('collection_success','collection_failure')
          {boundary}
    """), params).scalar_one())
