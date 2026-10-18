"""Isolated scratch migration 0001->0013, index and rollback smoke test.

Requires BF4PS_DATABASE_URL pointing to an explicitly named scratch DB.
"""
from __future__ import annotations
import os
import subprocess
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

url = os.environ['BF4PS_DATABASE_URL']
parsed = make_url(url)
if parsed.database != 'bf4ps_ranking_scratch' or parsed.host not in ('127.0.0.1', 'localhost'):
    raise SystemExit('REFUSING: scratch database name and loopback host required')
engine = create_engine(url)
with engine.connect() as c:
    db = c.execute(text('SELECT current_database()')).scalar_one()
    if db != 'bf4ps_ranking_scratch':
        raise SystemExit('REFUSING: database mismatch')

def alembic(*args):
    subprocess.run(['python', '-m', 'alembic', *args], check=True)

alembic('upgrade', '0012_manual_verify_api')
alembic('upgrade', 'head')
with engine.begin() as c:
    assert c.execute(text('SELECT version_num FROM alembic_version')).scalar_one() == '0013_indexed_equipment_rankings'
    for table, expected in [('weapon_leaderboard_metrics', 3), ('vehicle_leaderboard_metrics', 2)]:
        found = c.execute(text('SELECT count(*) FROM pg_indexes WHERE schemaname = :schema AND tablename = :table AND indexname LIKE :pattern'), {'schema':'public','table':table,'pattern':'ix_%_top'}).scalar_one()
        assert found == expected, (table, found)
    print('PASS: 0013 applied, all five ordering indexes exist')
alembic('downgrade', '0012_manual_verify_api')
with engine.connect() as c:
    assert c.execute(text('SELECT version_num FROM alembic_version')).scalar_one() == '0012_manual_verify_api'
    assert c.execute(text("SELECT to_regclass('public.weapon_leaderboard_metrics') IS NULL AND to_regclass('public.vehicle_leaderboard_metrics') IS NULL")).scalar_one()
print('PASS: downgrade to 0012 removes both derived tables')
alembic('upgrade', 'head')
print('PASS: repeat upgrade to 0013')
