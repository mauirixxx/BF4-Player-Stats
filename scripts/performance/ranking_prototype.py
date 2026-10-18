#!/usr/bin/env python3
"""Isolated PostgreSQL indexed-ranking prototype; never writes to BF4PS production.

Usage: BF4PS_RANKING_SCRATCH_URL=postgresql+psycopg://.../bf4ps_ranking_scratch \
       python scripts/performance/ranking_prototype.py

Uses deterministic synthetic soldiers, with explicit score threshold and tie tests.
"""
from __future__ import annotations
import os
import statistics
import time
from sqlalchemy import create_engine, text

DB = os.environ.get('BF4PS_RANKING_SCRATCH_URL', '')
if not DB or 'bf4ps_ranking_scratch' not in DB.rsplit('/', 1)[-1].split('?')[0]:
    raise SystemExit('REFUSING: BF4PS_RANKING_SCRATCH_URL must target bf4ps_ranking_scratch')
engine = create_engine(DB, pool_pre_ping=True)
with engine.begin() as conn:
    name = conn.execute(text('SELECT current_database()')).scalar_one()
    if name != 'bf4ps_ranking_scratch':
        raise SystemExit('REFUSING: connected database is not bf4ps_ranking_scratch')
    conn.execute(text('SET LOCAL statement_timeout = 120000'))
    conn.execute(text('CREATE SCHEMA IF NOT EXISTS ranking_prototype'))
    conn.execute(text('DROP TABLE IF EXISTS ranking_prototype.weapon_rank CASCADE'))
    conn.execute(text('DROP TABLE IF EXISTS ranking_prototype.vehicle_rank CASCADE'))
    conn.execute(text('DROP TABLE IF EXISTS ranking_prototype.weapon_raw CASCADE'))
    conn.execute(text('DROP TABLE IF EXISTS ranking_prototype.vehicle_raw CASCADE'))
    conn.execute(text('''CREATE TABLE ranking_prototype.weapon_raw (
        soldier_id bigint NOT NULL, weapon_id bigint NOT NULL, kills bigint NOT NULL,
        time_equipped_seconds bigint NOT NULL, shots_fired bigint NOT NULL,
        shots_hit bigint NOT NULL, PRIMARY KEY(soldier_id,weapon_id))'''))
    conn.execute(text('''CREATE TABLE ranking_prototype.vehicle_raw (
        soldier_id bigint NOT NULL, vehicle_id bigint NOT NULL, kills bigint NOT NULL,
        time_in_seconds bigint NOT NULL, PRIMARY KEY(soldier_id,vehicle_id))'''))
    conn.execute(text('''INSERT INTO ranking_prototype.weapon_raw
        SELECT id,5,(id*47)%6000,(id*31)%25000,(id*19)%15000,
        LEAST((id*11)%14000,(id*19)%15000)
        FROM generate_series(1,100000) id'''))
    conn.execute(text('''INSERT INTO ranking_prototype.vehicle_raw
        SELECT id,1,(id*37)%2500,(id*41)%20000
        FROM generate_series(1,100000) id'''))
    conn.execute(text('''CREATE TABLE ranking_prototype.weapon_rank AS
        SELECT soldier_id,weapon_id,kills,
          CASE WHEN time_equipped_seconds>=60 THEN kills::numeric*60/time_equipped_seconds END AS kpm,
          CASE WHEN shots_fired>=100 AND shots_hit<=shots_fired THEN shots_hit::numeric*100/shots_fired END AS accuracy
        FROM ranking_prototype.weapon_raw'''))
    conn.execute(text('''CREATE TABLE ranking_prototype.vehicle_rank AS
        SELECT soldier_id,vehicle_id,kills,
          CASE WHEN time_in_seconds>=60 THEN kills::numeric*60/time_in_seconds END AS kpm
        FROM ranking_prototype.vehicle_raw'''))
    for table,metric in [('weapon_rank','kills'),('weapon_rank','kpm'),('weapon_rank','accuracy'),('vehicle_rank','kills'),('vehicle_rank','kpm')]:
        col = 'weapon_id' if table == 'weapon_rank' else 'vehicle_id'
        conn.execute(text(f'''CREATE INDEX {table}_{metric}_idx
            ON ranking_prototype.{table} ({col}, {metric} DESC NULLS LAST, soldier_id)'''))
    for table in ['weapon_raw','vehicle_raw','weapon_rank','vehicle_rank']:
        conn.execute(text(f'ANALYZE ranking_prototype.{table}'))

queries = {
    'weapon kills': ('weapon_raw','weapon_rank','weapon_id','kills','kills'),
    'weapon KPM': ('weapon_raw','weapon_rank','weapon_id','kills::numeric*60/NULLIF(time_equipped_seconds,0)','kpm'),
    'weapon accuracy': ('weapon_raw','weapon_rank','weapon_id','shots_hit::numeric*100/NULLIF(shots_fired,0)','accuracy'),
    'vehicle kills': ('vehicle_raw','vehicle_rank','vehicle_id','kills','kills'),
    'vehicle KPM': ('vehicle_raw','vehicle_rank','vehicle_id','kills::numeric*60/NULLIF(time_in_seconds,0)','kpm'),
}
with engine.connect() as conn:
    conn.execute(text('SET TRANSACTION READ ONLY'))
    conn.execute(text("SET LOCAL statement_timeout = '30000ms'"))
    for label,(raw,derived,idcol,expression,metric) in queries.items():
        condition = ('time_equipped_seconds>=60' if label=='weapon KPM' else
                     'shots_fired>=100 AND shots_hit<=shots_fired' if label=='weapon accuracy' else
                     'time_in_seconds>=60' if label=='vehicle KPM' else 'TRUE')
        old = f'''SELECT soldier_id,{expression} AS score FROM ranking_prototype.{raw}
                  WHERE {idcol}=:item AND {condition} ORDER BY score DESC NULLS LAST,soldier_id LIMIT 10'''
        new = f'''SELECT soldier_id,{metric} AS score FROM ranking_prototype.{derived}
                  WHERE {idcol}=:item AND {metric} IS NOT NULL ORDER BY {metric} DESC NULLS LAST,soldier_id LIMIT 10'''
        old_rows=conn.execute(text(old),{'item':5 if raw=='weapon_raw' else 1}).all()
        new_rows=conn.execute(text(new),{'item':5 if raw=='weapon_raw' else 1}).all()
        assert old_rows==new_rows, (label,old_rows,new_rows)
        for variant,sql in [('raw',old),('indexed',new)]:
            plans=conn.execute(text('EXPLAIN (ANALYZE,BUFFERS,FORMAT TEXT) '+sql),{'item':5 if raw=='weapon_raw' else 1}).scalars().all()
            print(f'\n{label} {variant}: '+next(x for x in plans if x.startswith('Execution Time:')))
            print('\n'.join(plans[:5]))
        print('PARITY PASS: top 10 identities and exact numeric scores')
print('\nSCRATCH PROTOTYPE COMPLETE: no production tables modified')
