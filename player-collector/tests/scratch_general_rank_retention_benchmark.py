"""Scratch-only measured retention deletions; bounded to three generations."""
import os,time,json
from sqlalchemy import create_engine,text
from bf4ps.general_rank_retention import prune_one
e=create_engine(os.environ['BF4PS_DATABASE_URL'])
with e.connect() as c:
 assert c.execute(text('select current_database()')).scalar_one()=='bf4ps_rank_scratch'
 assert c.execute(text('select version_num from alembic_version')).scalar_one()=='0026_general_rank_snapshots'
before=None
with e.connect() as c:
 before=c.execute(text('select pg_current_wal_lsn()')).scalar_one()
print('START',str(before),flush=True)
for i in range(3):
 start=time.monotonic()
 with e.begin() as c:
  deleted=prune_one(c)
 elapsed=time.monotonic()-start
 with e.connect() as c:
  lsn=c.execute(text('select pg_current_wal_lsn()')).scalar_one()
  wal=c.execute(text('select pg_wal_lsn_diff(CAST(:a AS pg_lsn),CAST(:b AS pg_lsn))'),{'a':str(lsn),'b':str(before)}).scalar_one()
  pointers=c.execute(text('select count(*) from general_rank_published')).scalar_one()
 print('RESULT',json.dumps({'iteration':i+1,'deleted_generation':deleted,'elapsed_seconds':round(elapsed,3),'cumulative_wal_bytes':int(wal),'published_scopes':pointers}),flush=True)
 assert pointers==56
 before=lsn
 if deleted is None:break
e.dispose()
