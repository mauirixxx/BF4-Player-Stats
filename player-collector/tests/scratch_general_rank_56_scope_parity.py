"""Scratch-only 56-scope full-cohort parity, one publication per scope.
Requires explicit scratch database identity. Does not touch production.
"""
import os,time,importlib.util,json
from sqlalchemy import create_engine,text
from bf4ps.general_rank_publisher import METRICS,PLATFORMS,build_scope
from bf4ps.general_rank_reader import query_page as snapshot
spec=importlib.util.spec_from_file_location('legacy','/opt/bf4ps-general-rank-scratch/website/api/general_leaderboard.py')
legacy=importlib.util.module_from_spec(spec);spec.loader.exec_module(legacy)
engine=create_engine(os.environ['BF4PS_DATABASE_URL'],pool_pre_ping=True)
with engine.connect() as c:
    db=c.execute(text('select current_database()')).scalar_one()
    revision=c.execute(text('select version_num from alembic_version')).scalar_one()
    assert (db,revision)==('bf4ps_rank_scratch','0026_general_rank_snapshots')
print('START',db,revision,flush=True)
passed=0
for metric in METRICS:
 for platform in PLATFORMS:
  started=time.monotonic()
  with engine.begin() as c:
   generation,population=build_scope(c,metric,platform)
  with engine.connect().execution_options(isolation_level='REPEATABLE READ') as c:
   c.execute(text('SET TRANSACTION READ ONLY'))
   for case in ({},{'division':1},{'page':100},{'search':'bench_999'}):
    old=legacy.query_page(c,metric,platform,**case)
    new=snapshot(c,metric,platform,**case)
    assert new is not None
    new={k:v for k,v in new.items() if k not in ('published_at','generation_id')}
    if old!=new:
     differences=[k for k in old if old[k]!=new.get(k)]
     raise AssertionError(f'{metric}/{platform} {case} mismatch {differences}')
  passed+=1
  print('PASS',passed,'/56',metric,platform,'generation',generation,'population',population,'seconds',round(time.monotonic()-started,2),flush=True)
print('ALL 56 SCOPES PASSED',flush=True)
