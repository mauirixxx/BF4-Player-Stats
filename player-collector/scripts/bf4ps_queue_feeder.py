#!/usr/bin/env python3
"""Bounded production bootstrap queue replenishment; no Battlelog requests."""
from __future__ import annotations
import os
from sqlalchemy import create_engine, text

RESOURCES=('detailed','weapons','vehicles','profile')
TARGET=240
BATCH=80

def run():
    engine=create_engine(os.environ['BF4PS_DATABASE_URL'],pool_pre_ping=True)
    with engine.begin() as conn:
        conn.execute(text("SET LOCAL statement_timeout='20000ms'"))
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('bf4ps:production-bootstrap-feeder'))"))
        if conn.execute(text('SELECT current_database()')).scalar_one()!='bf4_playerstats':
            raise RuntimeError('Wrong database')
        revision=conn.execute(text('SELECT version_num FROM alembic_version')).scalar_one()
        if revision!='0027_soldier_ban_status':
            raise RuntimeError(f'Unexpected Alembic revision: {revision}')
        actionable=conn.execute(text("""SELECT count(*) FROM collection_jobs
            WHERE lane='background' AND (status IN ('claimed','running')
              OR (status='pending' AND eligible_at<=now()))""")).scalar_one()
        budget=min(BATCH,max(0,TARGET-actionable))
        created={}
        for resource in RESOURCES:
            if budget<=0:break
            # Names are from a fixed allowlist, never from user input.
            rows=conn.execute(text(f"""SELECT s.soldier_id FROM soldiers s
              JOIN collection_state cs ON cs.soldier_id=s.soldier_id
              WHERE s.platform IN ('pc','ps4','xboxone')
                AND cs.{resource}_state='never_attempted'
                AND NOT EXISTS (SELECT 1 FROM collection_jobs j
                  WHERE j.soldier_id=s.soldier_id AND j.resource=:resource)
                AND NOT EXISTS (SELECT 1 FROM player_exclusions e
                  WHERE e.platform=s.platform AND e.persona_id=s.persona_id AND e.active)
              ORDER BY s.soldier_id LIMIT :limit"""),{'resource':resource,'limit':min(budget,20)}).scalars().all()
            n=0
            for soldier_id in rows:
                result=conn.execute(text("""INSERT INTO collection_jobs
                  (soldier_id,resource,lane,priority_class,reason,status,priority_value,eligible_at)
                  VALUES (:sid,:resource,'background','bootstrap','continuous_bootstrap','pending',0,now())
                  ON CONFLICT (soldier_id,resource) DO NOTHING"""),{'sid':soldier_id,'resource':resource})
                n+=result.rowcount
            created[resource]=n
            budget-=n
        print(f'actionable_before={actionable} created={created} target={TARGET}',flush=True)
    engine.dispose()

if __name__=='__main__':run()
