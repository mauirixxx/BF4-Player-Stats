"""Shared frozen contract/helpers for Phase 3E Lifecycle A."""
from __future__ import annotations
from dataclasses import dataclass
from uuid import UUID
from sqlalchemy import text

EXPECTED_DATABASE="bf4_playerstats_test"; EXPECTED_DB_HOST="mak-db-02.bf4statusbot.com"; EXPECTED_REVISION="0003_request_gates"
PLATFORMS=("pc","ps4","xboxone"); PER_PLATFORM=120; GLOBAL_ATTEMPT_CEILING=360; TARGET_DEPTH=6
REQUEST_INTERVAL_SECONDS=5.0; LEASE_SECONDS=120; TARGET_HOST="hnl-01"

@dataclass(frozen=True)
class FrozenHost:
    collector_uuid: UUID; collector_name: str; egress_key: str
HOSTS={
 "hnl-01":FrozenHost(UUID("b2b3ef60-62e8-4d4a-91b0-41a2e2a3e001"),"phase3e-hnl-01","phase3e-hnl-01"),
 "kah-01":FrozenHost(UUID("b2b3ef60-62e8-4d4a-91b0-41a2e2a3e002"),"phase3e-kah-01","phase3e-kah-01"),
 "tcou":FrozenHost(UUID("b2b3ef60-62e8-4d4a-91b0-41a2e2a3e003"),"phase3e-tcou","phase3e-tcou"),
}
FROZEN_UUIDS=tuple(h.collector_uuid for h in HOSTS.values())
# Exact IDs captured by the reviewed 2026-10-04 read-only 360-row manifest.
COHORT_BY_PLATFORM={
 "pc":tuple(range(269,389)),
 "ps4":tuple(range(928,943))+tuple(range(8635,8680))+tuple(range(8681,8741)),
 "xboxone":tuple(range(1027,1147)),
}
COHORT_SOLDIER_IDS=tuple(s for p in PLATFORMS for s in COHORT_BY_PLATFORM[p])
assert all(len(COHORT_BY_PLATFORM[p])==PER_PLATFORM for p in PLATFORMS)
assert len(COHORT_SOLDIER_IDS)==GLOBAL_ATTEMPT_CEILING and len(set(COHORT_SOLDIER_IDS))==GLOBAL_ATTEMPT_CEILING

def assert_target(conn)->None:
 row=conn.execute(text("SELECT current_database() database_name, pg_is_in_recovery() recovery, current_setting('transaction_read_only') read_only")).mappings().one()
 revision=conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
 if row['database_name']!=EXPECTED_DATABASE or row['recovery'] or row['read_only']!='off': raise RuntimeError('Lifecycle A database safety boundary failed')
 if revision!=EXPECTED_REVISION: raise RuntimeError(f'unexpected Alembic revision {revision!r}')
