"""Scratch-only collision tests: lock contention, collector/backfill, opposite resources."""
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic
from sqlalchemy import create_engine,text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from bf4ps.ranking_backfill import refresh_soldier_metrics,process_window
u=make_url(os.environ['BF4PS_DATABASE_URL'])
assert u.database=='bf4ps_ranking_scratch' and u.host in ('127.0.0.1','localhost')
e=create_engine(os.environ['BF4PS_DATABASE_URL'],pool_size=4,max_overflow=0)
with e.connect() as c:
 assert c.execute(text('SELECT version_num FROM alembic_version')).scalar_one()=='0013_indexed_equipment_rankings'
 soldier=c.execute(text('SELECT soldier_id FROM weapon_leaderboard_metrics GROUP BY soldier_id ORDER BY soldier_id LIMIT 1')).scalar_one()
 baseline=c.execute(text('SELECT count(*) FROM weapon_leaderboard_metrics WHERE soldier_id=:s'),{'s':soldier}).scalar_one()
lock=text("SELECT pg_advisory_xact_lock(hashtextextended('bf4ps:ranking:' || CAST(:s AS text), 0))")
try_lock=text("SELECT pg_try_advisory_xact_lock(hashtextextended('bf4ps:ranking:' || CAST(:s AS text), 0))")
with e.connect() as a, e.connect() as b:
 ta=a.begin();tb=b.begin()
 try:
  a.execute(lock,{'s':soldier})
  assert b.execute(try_lock,{'s':soldier}).scalar_one() is False
  print('PASS: competing transaction cannot acquire occupied soldier lock',flush=True)
 finally: tb.rollback();ta.rollback()
with e.begin() as c:
 assert c.execute(try_lock,{'s':soldier}).scalar_one() is True
print('PASS: lock released at transaction rollback',flush=True)
# While owner holds lock, backfill must time out BEFORE deleting metrics.
with e.connect() as owner, e.connect() as rival:
 t=owner.begin()
 try:
  owner.execute(lock,{'s':soldier})
  with rival.begin():
   rival.execute(text("SET LOCAL lock_timeout='350ms'"))
   try: process_window(rival,soldier,soldier+1)
   except OperationalError as exc:
    assert 'lock timeout' in str(exc).lower(),str(exc)
   else: raise AssertionError('backfill bypassed occupied soldier lock')
 finally:t.rollback()
with e.connect() as c:
 assert c.execute(text('SELECT count(*) FROM weapon_leaderboard_metrics WHERE soldier_id=:s'),{'s':soldier}).scalar_one()==baseline
print('PASS: backfill collision times out safely; indexed baseline unchanged',flush=True)
# Opposing resource refreshes for one soldier, genuinely overlapping connections.
entered=Event();release=Event()
def first():
 with e.connect() as c:
  tx=c.begin()
  try:
   c.execute(lock,{'s':soldier});entered.set()
   assert release.wait(8)
   refresh_soldier_metrics(c,soldier,'weapons')
  finally:tx.rollback()
def second():
 assert entered.wait(8)
 with e.connect() as c:
  tx=c.begin()
  try:
   c.execute(text("SET LOCAL lock_timeout='8000ms'"))
   start=monotonic();refresh_soldier_metrics(c,soldier,'vehicles')
   return monotonic()-start
  finally:tx.rollback()
with ThreadPoolExecutor(max_workers=2) as pool:
 a=pool.submit(first);b=pool.submit(second)
 assert entered.wait(8)
 # Release after the second worker starts; lock conflict is already checked above.
 release.set();a.result();duration=b.result()
print('PASS: opposite resource refreshes complete on same soldier; wait seconds',round(duration,3),flush=True)
# Backfill succeeds after lock owner exits.
with e.connect() as c:
 tx=c.begin()
 try:
  process_window(c,soldier,soldier+1)
  assert c.execute(text('SELECT count(*) FROM weapon_leaderboard_metrics WHERE soldier_id=:s'),{'s':soldier}).scalar_one()==baseline
 finally:tx.rollback()
print('PASS: backfill resumes successfully after contention',flush=True)
print('PASS: scratch collision suite',flush=True)
