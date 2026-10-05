"""Frozen contract/helpers for Phase 3E Lifecycle B."""
from __future__ import annotations
import os
from uuid import UUID
from urllib.parse import urlsplit
from sqlalchemy import text

EXPECTED_DATABASE="bf4_playerstats_test"
EXPECTED_DB_HOST="mak-db-02.bf4statusbot.com"
EXPECTED_REVISION="0003_request_gates"
VICTIM_HOST="hnl-01"
RECLAIMER_HOST="kah-01"
VICTIM_UUID=UUID("b2b3ef60-62e8-4d4a-91b0-41a2e2a3e001")
RECLAIMER_UUID=UUID("b2b3ef60-62e8-4d4a-91b0-41a2e2a3e002")
VICTIM_NAME="phase3e-hnl-01"
RECLAIMER_NAME="phase3e-kah-01"
LEASE_SECONDS=30
RESOURCE="detailed"
LANE="background"


def database_url()->str:
    url=os.environ.get("BF4PS_DATABASE_URL","")
    p=urlsplit(url)
    if not url or p.hostname!=EXPECTED_DB_HOST or p.path.lstrip("/")!=EXPECTED_DATABASE:
        raise SystemExit("REFUSING: wrong database target")
    return url


def assert_target(conn)->None:
    row=conn.execute(text("SELECT current_database() database_name, pg_is_in_recovery() recovery, current_setting('transaction_read_only') read_only")).mappings().one()
    rev=conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    if row['database_name']!=EXPECTED_DATABASE or row['recovery'] or row['read_only']!='off':
        raise RuntimeError("Lifecycle B database safety boundary failed")
    if rev!=EXPECTED_REVISION:
        raise RuntimeError(f"unexpected Alembic revision {rev!r}")
