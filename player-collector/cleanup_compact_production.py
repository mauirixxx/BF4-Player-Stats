"""Conservative production compact retention. Dry-run by default.

Never delete a published pointer, a generation with legacy rows, or one of
the newest two compact generations per scope. Bounded batches limit WAL.
"""
import argparse
import os
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

QUERY=text("""WITH ordered AS (
 SELECT g.generation_id,
 row_number() OVER (PARTITION BY g.kind,g.item_id,g.platform,g.metric
 ORDER BY g.created_at DESC,g.generation_id DESC) AS recency
 FROM equipment_rank_generations g
 WHERE g.snapshot_format=2 AND g.status='published'
 AND EXISTS (SELECT 1 FROM equipment_rank_compact_blocks b WHERE b.generation_id=g.generation_id)
)
SELECT o.generation_id FROM ordered o
WHERE o.recency>:keep
 AND NOT EXISTS (SELECT 1 FROM equipment_rank_compact_published p WHERE p.generation_id=o.generation_id)
 AND NOT EXISTS (SELECT 1 FROM equipment_rank_published p WHERE p.generation_id=o.generation_id)
 AND NOT EXISTS (SELECT 1 FROM equipment_rank_rows r WHERE r.generation_id=o.generation_id)
 ORDER BY o.generation_id LIMIT :limit""")

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--execute',action='store_true')
    p.add_argument('--production-ack',action='store_true')
    p.add_argument('--keep',type=int,default=2)
    p.add_argument('--limit',type=int,default=1)
    p.add_argument('--statement-timeout-ms',type=int,default=15000)
    p.add_argument('--lock-timeout-ms',type=int,default=1000)
    a=p.parse_args()
    if a.keep<2 or not 1<=a.limit<=20: p.error('unsafe retention bounds')
    if not 1000<=a.statement_timeout_ms<=30000 or not 100<=a.lock_timeout_ms<=3000:
        p.error('unsafe timeout bounds')
    url=os.environ['BF4PS_DATABASE_URL']
    if make_url(url).database!='bf4_playerstats' or not a.production_ack:
        p.error('requires explicit production authorization')
    engine=create_engine(url,pool_pre_ping=True)
    try:
        with engine.begin() as c:
            c.execute(text('SET LOCAL statement_timeout = :ms'.replace(':ms', str(a.statement_timeout_ms))))
            c.execute(text('SET LOCAL lock_timeout = :ms'.replace(':ms', str(a.lock_timeout_ms))))
            if c.execute(text('SELECT version_num FROM alembic_version')).scalar_one() not in ('0023_compact_exclusion_guard', '0024_profile_lookup_idx'):
                raise RuntimeError('unexpected schema revision')
            ids=c.execute(QUERY,{'keep':a.keep,'limit':a.limit}).scalars().all()
            print('eligible compact generations',ids,flush=True)
            if not a.execute or not ids: return
            # Recheck eligibility inside the deletion transaction. Serializing
            # with the ranking capacity lock prevents a competing rank claim.
            c.execute(text('SELECT id FROM equipment_rank_capacity WHERE id=1 FOR UPDATE NOWAIT'))
            current=set(c.execute(QUERY,{'keep':a.keep,'limit':a.limit}).scalars().all())
            safe=[i for i in ids if i in current]
            if safe:
                c.execute(text('DELETE FROM equipment_rank_generations WHERE generation_id=ANY(:ids)'),{'ids':safe})
            print('deleted compact generations',safe,flush=True)
    finally: engine.dispose()

if __name__=='__main__': main()
