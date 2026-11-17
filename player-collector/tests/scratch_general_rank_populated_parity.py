"""Scratch-only fill 11 missing metric fixtures and compare all 44 populated scopes."""
import os,time,importlib.util
from sqlalchemy import create_engine,text
from bf4ps.general_rank_publisher import METRICS,PLATFORMS,build_scope
from bf4ps.general_rank_reader import query_page as snapshot
spec=importlib.util.spec_from_file_location('legacy','/opt/bf4ps-general-rank-scratch/website/api/general_leaderboard.py')
legacy=importlib.util.module_from_spec(spec);spec.loader.exec_module(legacy)
engine=create_engine(os.environ['BF4PS_DATABASE_URL'])
with engine.connect() as c:
 assert c.execute(text('select current_database()')).scalar_one()=='bf4ps_rank_scratch'
 assert c.execute(text('select version_num from alembic_version')).scalar_one()=='0026_general_rank_snapshots'
metrics=[m for m in METRICS if m not in ('kills','wins','time_played_seconds')]
# 1200 rows, 400 per platform; intentionally ties and zeros.
assignments=', '.join(f'{m}=(d.soldier_id % {71+i*11})' for i,m in enumerate(metrics))
with engine.begin() as c:
 n=c.execute(text(f"""WITH chosen AS (
 SELECT d2.soldier_id FROM detailed_stats_current d2
 JOIN soldiers s ON s.soldier_id=d2.soldier_id
 WHERE s.platform IN ('pc','ps4','xboxone')
 ORDER BY d2.soldier_id LIMIT 1200
 )
 UPDATE detailed_stats_current d SET {assignments}
 FROM chosen WHERE d.soldier_id=chosen.soldier_id""")).rowcount
 print('seeded',n,'rows for',len(metrics),'metrics',flush=True)
assert n==1200,n
passed=0
for metric in metrics:
 for platform in PLATFORMS:
  start=time.monotonic()
  with engine.begin() as c: generation,pop=build_scope(c,metric,platform)
  assert pop>0,(metric,platform,pop)
  with engine.connect().execution_options(isolation_level='REPEATABLE READ') as c:
   c.execute(text('SET TRANSACTION READ ONLY'))
   for case in ({},{'division':1},{'page':2,'page_size':20},{'search':'bench_999'}):
    old=legacy.query_page(c,metric,platform,**case)
    new=snapshot(c,metric,platform,**case)
    assert new is not None
    new={k:v for k,v in new.items() if k not in ('published_at','generation_id')}
    if old!=new:
     raise AssertionError((metric,platform,case,[k for k in old if old[k]!=new.get(k)]))
  passed+=1
  print('PASS',passed,'/44',metric,platform,'population',pop,'seconds',round(time.monotonic()-start,2),flush=True)
print('ALL 44 PREVIOUSLY EMPTY SCOPES PASSED WITH POPULATED DATA',flush=True)
