"""Two-phase equipment ranking builder. No Battlelog traffic.
Build on a repeatable-read snapshot without scope locks; publish only if the
scope version remains identical under a short row lock. Default: dry-run.
"""
import argparse,os,time,uuid
from sqlalchemy import create_engine,text
from sqlalchemy.engine import make_url

def main():
 p=argparse.ArgumentParser()
 p.add_argument('--kind',choices=('weapon','vehicle'),required=True)
 p.add_argument('--item',type=int,required=True)
 p.add_argument('--platform',choices=('pc','ps4','xboxone','all'),required=True)
 p.add_argument('--metric',choices=('kills','kpm','accuracy'),required=True)
 p.add_argument('--publish',action='store_true')
 p.add_argument('--production-ack',action='store_true')
 p.add_argument('--rank-worker-id',type=uuid.UUID)
 p.add_argument('--rank-claim-token',type=uuid.UUID)
 p.add_argument('--rank-claim-epoch',type=int)
 a=p.parse_args()
 fenced=any(x is not None for x in (a.rank_worker_id,a.rank_claim_token,a.rank_claim_epoch))
 if fenced and not all(x is not None for x in (a.rank_worker_id,a.rank_claim_token,a.rank_claim_epoch)):p.error('all claim credentials required')
 if a.item<1 or (a.kind=='vehicle' and a.metric=='accuracy'):p.error('invalid metric/item')
 url=os.environ['BF4PS_DATABASE_URL']; db=make_url(url).database
 if db not in ('bf4ps_ranking_scratch','bf4_playerstats'):p.error('unexpected database')
 if a.publish and db=='bf4_playerstats' and not a.production_ack:p.error('production publication requires --production-ack')
 if db=='bf4_playerstats' and os.getenv('BF4PS_DISTRIBUTED_RANK_REQUIRED')=='1' and a.publish and not fenced:p.error('unfenced production publishing disabled')
 table='weapon_leaderboard_metrics' if a.kind=='weapon' else 'vehicle_leaderboard_metrics'
 col='weapon_id' if a.kind=='weapon' else 'vehicle_id'
 params=dict(kind=a.kind,item=a.item,platform=a.platform,metric=a.metric)
 e=create_engine(url,pool_pre_ping=True); start=time.monotonic()
 with e.connect().execution_options(isolation_level='REPEATABLE READ') as c:
  actual,revision=c.execute(text('select current_database(),(select version_num from alembic_version)')).one()
  if actual!=db or revision not in ('0017_rank_immutable_scores','0018_distributed_rank_queue'):raise RuntimeError('wrong database/revision')
  if fenced and revision!='0018_distributed_rank_queue':raise RuntimeError('distributed claim requires migration 0018')
  c.execute(text("SET LOCAL statement_timeout='120s'"))
  # Ranking-only memory budget; never change PostgreSQL's global work_mem.
  c.execute(text("SET LOCAL work_mem='32MB'"))
  version=c.execute(text("""SELECT version FROM equipment_rank_scope_versions
   WHERE kind=:kind AND item_id=:item AND platform=:platform"""),params).scalar_one_or_none()
  if version is None:raise RuntimeError('scope version missing: refusing untracked generation')
  count=c.execute(text(f"""SELECT count(*) FROM {table} m JOIN soldiers s ON s.soldier_id=m.soldier_id
   WHERE m.{col}=:item AND (:platform='all' OR s.platform=:platform)
   AND NOT EXISTS(SELECT 1 FROM player_exclusions x WHERE x.platform=s.platform
   AND x.persona_id=s.persona_id AND x.active)"""),params).scalar_one()
  expected=c.execute(text("""SELECT coalesce(sum(population),0) FROM equipment_population
   WHERE kind=:kind AND item_id=:item AND (:platform='all' OR platform=:platform)"""),params).scalar_one()
  if count!=expected:raise RuntimeError(f'population mismatch {count} vs {expected}')
  gen=c.execute(text("""INSERT INTO equipment_rank_generations(kind,item_id,platform,metric,snapshot_format)
   VALUES (:kind,:item,:platform,:metric,1) RETURNING generation_id"""),params).scalar_one()
  inserted=c.execute(text(f"""INSERT INTO equipment_rank_rows(generation_id,soldier_id,rank,position,
    snapshot_kills,snapshot_kpm,snapshot_accuracy,snapshot_source_fetched_at)
   SELECT :g,soldier_id,rank() OVER(ORDER BY score DESC NULLS LAST),
   row_number() OVER(ORDER BY score DESC NULLS LAST,soldier_id),
   kills,kpm,accuracy,source_fetched_at
   FROM (SELECT m.soldier_id,m.{a.metric} AS score,m.kills,m.kpm,
    {'m.accuracy' if a.kind=='weapon' else 'NULL::numeric'} AS accuracy,
    m.source_fetched_at FROM {table} m
   JOIN soldiers s ON s.soldier_id=m.soldier_id
   WHERE m.{col}=:item AND (:platform='all' OR s.platform=:platform)
   AND NOT EXISTS(SELECT 1 FROM player_exclusions x WHERE x.platform=s.platform
   AND x.persona_id=s.persona_id AND x.active)) eligible"""),{**params,'g':gen}).rowcount
  if inserted!=count:raise RuntimeError(f'insert mismatch {inserted} vs {count}')
  c.execute(text(f"""UPDATE equipment_rank_generations SET status='validated',snapshot_format=1,row_count=:n,
   input_scope_version=:v,completed_at=now(),
   input_max_fetched_at=(SELECT max(m.source_fetched_at) FROM {table} m
   JOIN soldiers s ON s.soldier_id=m.soldier_id
   WHERE m.{col}=:item AND (:platform='all' OR s.platform=:platform))
   WHERE generation_id=:g"""),{**params,'n':count,'v':version,'g':gen})
  if not a.publish:
   c.rollback();print(dict(database=db,mode='rollback',rows=count,version=version,seconds=round(time.monotonic()-start,2)),flush=True);return
  c.commit()
 # New transaction: lock only during pointer swap, never during rank calculation.
 with e.begin() as c:
  c.execute(text("SET LOCAL lock_timeout='3s'"))
  # Snapshot captures scores consistently; subsequent collector updates are expected.
  # An hourly snapshot remains valid after ordinary metric updates.
  # Exclusion safety is checked independently by the website reader.
  if fenced:
   # Serialize publication against lease renewal/reclaim and verify current ownership.
   owned=c.execute(text("""SELECT 1 FROM equipment_rank_jobs
      WHERE kind=:kind AND item_id=:item AND platform=:platform AND metric=:metric
        AND claimed_by=:worker AND claim_token=:token AND claim_epoch=:epoch
        AND lease_expires_at>clock_timestamp() FOR UPDATE"""),
      {**params,'worker':a.rank_worker_id,'token':a.rank_claim_token,'epoch':a.rank_claim_epoch}).scalar_one_or_none()
   if owned is None:raise RuntimeError('ranking claim expired or fenced: publication denied')
  previous=c.execute(text("""SELECT generation_id FROM equipment_rank_published
   WHERE kind=:kind AND item_id=:item AND platform=:platform AND metric=:metric FOR UPDATE"""),params).scalar_one_or_none()
  c.execute(text("""INSERT INTO equipment_rank_published(kind,item_id,platform,metric,generation_id)
   VALUES (:kind,:item,:platform,:metric,:g)
   ON CONFLICT(kind,item_id,platform,metric) DO UPDATE
   SET generation_id=EXCLUDED.generation_id,published_at=now()"""),{**params,'g':gen})
  c.execute(text("UPDATE equipment_rank_generations SET status='published' WHERE generation_id=:g"),{'g':gen})
  if previous is not None and previous!=gen:
   c.execute(text("UPDATE equipment_rank_generations SET status='retired' WHERE generation_id=:g"),{'g':previous})
 print(dict(result='published',database=db,generation=gen,rows=count,version=version,seconds=round(time.monotonic()-start,2)),flush=True)
if __name__=='__main__':main()
