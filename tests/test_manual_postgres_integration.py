"""Opt-in real PostgreSQL concurrency test. NEVER targets production.

Requires an isolated database with Alembic revision 0009 installed and
BF4PS_MANUAL_TEST_DATABASE_URL pointing to a database named *_scratch or *_test.
The test creates and cleans up its own synthetic soldier and request evidence.
"""
import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
from urllib.parse import urlsplit

import pytest
from sqlalchemy import create_engine, text

from bf4ps.manual_request_admission import admit_registered_soldier

URL = os.getenv('BF4PS_MANUAL_TEST_DATABASE_URL')


def _test_engine():
    if not URL:
        pytest.skip('isolated PostgreSQL test database not configured')
    database = urlsplit(URL).path.lstrip('/')
    if not database.endswith(('_scratch', '_test')) or database == 'bf4_playerstats':
        pytest.fail('REFUSING non-scratch database for manual integration test')
    return create_engine(URL, pool_size=3, max_overflow=0)


def test_concurrent_first_requests_share_one_cooldown():
    engine = _test_engine()
    persona = 8_000_000_000_000_000_000 + (uuid4().int % 100_000_000)
    with engine.begin() as conn:
        soldier_id = conn.execute(text('''
            INSERT INTO soldiers (persona_id, platform, current_name,
                                  first_seen_at, last_seen_at)
            VALUES (:persona, 'pc', 'manual-test-synthetic', now(), now())
            RETURNING soldier_id
        '''), {'persona': persona}).scalar_one()
    try:
        def submit(_):
            with engine.begin() as conn:
                return admit_registered_soldier(conn, soldier_id=soldier_id)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(submit, range(2)))
        assert sum(r.accepted for r in results) == 1
        assert sum(not r.accepted for r in results) == 1
        assert {r.request_id for r in results} == {next(r.request_id for r in results if r.accepted)}
        with engine.connect() as conn:
            assert conn.execute(text('''
                SELECT count(*) FROM manual_collection_requests WHERE soldier_id = :id
            '''), {'id': soldier_id}).scalar_one() == 1
            assert conn.execute(text('''
                SELECT count(*) FROM collection_jobs WHERE soldier_id = :id
            '''), {'id': soldier_id}).scalar_one() == 4
    finally:
        with engine.begin() as conn:
            conn.execute(text('DELETE FROM manual_request_cooldowns WHERE soldier_id = :id'), {'id': soldier_id})
            conn.execute(text('DELETE FROM manual_collection_requests WHERE soldier_id = :id'), {'id': soldier_id})
            conn.execute(text('DELETE FROM collection_jobs WHERE soldier_id = :id'), {'id': soldier_id})
            conn.execute(text('DELETE FROM soldiers WHERE soldier_id = :id'), {'id': soldier_id})
        engine.dispose()