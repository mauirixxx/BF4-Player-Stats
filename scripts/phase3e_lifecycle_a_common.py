"""Shared frozen contract/helpers for Phase 3E Lifecycle A."""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID
from sqlalchemy import text

EXPECTED_DATABASE = "bf4_playerstats_test"
EXPECTED_DB_HOST = "mak-db-02.bf4statusbot.com"
EXPECTED_REVISION = "0003_request_gates"
PLATFORMS = ("pc", "ps4", "xboxone")
PER_PLATFORM = 120
GLOBAL_ATTEMPT_CEILING = 360
TARGET_DEPTH = 6
REQUEST_INTERVAL_SECONDS = 5.0
LEASE_SECONDS = 120
TARGET_HOST = "hnl-01"

@dataclass(frozen=True)
class FrozenHost:
    collector_uuid: UUID
    collector_name: str
    egress_key: str

HOSTS = {
    "hnl-01": FrozenHost(UUID("b2b3ef60-62e8-4d4a-91b0-41a2e2a3e001"), "phase3e-hnl-01", "phase3e-hnl-01"),
    "kah-01": FrozenHost(UUID("b2b3ef60-62e8-4d4a-91b0-41a2e2a3e002"), "phase3e-kah-01", "phase3e-kah-01"),
    "tcou": FrozenHost(UUID("b2b3ef60-62e8-4d4a-91b0-41a2e2a3e003"), "phase3e-tcou", "phase3e-tcou"),
}
FROZEN_UUIDS = tuple(host.collector_uuid for host in HOSTS.values())
EXPECTED_FIRST = {"pc": 269, "ps4": 928, "xboxone": 1027}
EXPECTED_LAST = {"pc": 388, "ps4": 8740, "xboxone": 1146}


def load_frozen_cohort(conn) -> tuple[tuple[int, ...], dict[str, tuple[int, ...]]]:
    """Reconstruct the reviewed deterministic Lifecycle A selection and verify boundaries."""
    rows = conn.execute(text("""
        SELECT s.soldier_id, s.platform
        FROM soldiers AS s
        JOIN collection_state AS cs ON cs.soldier_id = s.soldier_id
        LEFT JOIN detailed_stats_current AS dsc ON dsc.soldier_id = s.soldier_id
        WHERE s.platform IN ('pc','ps4','xboxone')
          AND cs.detailed_state = 'never_attempted'
          AND cs.detailed_last_attempt_at IS NULL
          AND cs.detailed_last_success_at IS NULL
          AND dsc.soldier_id IS NULL
          AND NOT EXISTS (
              SELECT 1 FROM collection_jobs AS cj
              WHERE cj.soldier_id = s.soldier_id AND cj.resource = 'detailed'
          )
        ORDER BY s.platform, s.soldier_id
    """)).mappings().all()
    by_platform: dict[str, tuple[int, ...]] = {}
    for platform in PLATFORMS:
        ids = tuple(int(r["soldier_id"]) for r in rows if str(r["platform"]) == platform)[:PER_PLATFORM]
        if len(ids) != PER_PLATFORM:
            raise RuntimeError(f"Lifecycle A lacks {PER_PLATFORM} pristine {platform} soldiers")
        if ids[0] != EXPECTED_FIRST[platform] or ids[-1] != EXPECTED_LAST[platform]:
            raise RuntimeError(f"Lifecycle A frozen {platform} selection drifted: {ids[0]}..{ids[-1]}")
        by_platform[platform] = ids
    ids = tuple(sid for platform in PLATFORMS for sid in by_platform[platform])
    if len(ids) != GLOBAL_ATTEMPT_CEILING or len(set(ids)) != GLOBAL_ATTEMPT_CEILING:
        raise RuntimeError("Lifecycle A frozen cohort cardinality/uniqueness failed")
    return ids, by_platform


def assert_target(conn) -> None:
    row = conn.execute(text("""
        SELECT current_database() AS database_name,
               pg_is_in_recovery() AS recovery,
               current_setting('transaction_read_only') AS read_only
    """)).mappings().one()
    revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    if row["database_name"] != EXPECTED_DATABASE or row["recovery"] or row["read_only"] != "off":
        raise RuntimeError("Lifecycle A database safety boundary failed")
    if revision != EXPECTED_REVISION:
        raise RuntimeError(f"unexpected Alembic revision {revision!r}")
