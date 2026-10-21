"""PostgreSQL admission for any number of ranking workers.

One capacity-row lock serializes admission. Job row locks prevent duplicate claims.
No expensive computation runs in the admission transaction.
"""
import uuid
from sqlalchemy import text

def register(engine, hostname, site=None):
    worker = uuid.uuid4()
    with engine.begin() as c:
        c.execute(text("""INSERT INTO equipment_rank_workers(worker_id,hostname,site)
                          VALUES(:w,:h,:s)"""), dict(w=worker,h=hostname,s=site))
    return worker

def discover(engine):
    """Idempotently populate every nonempty supported equipment scope."""
    with engine.begin() as c:
        return c.execute(text("""
            INSERT INTO equipment_rank_jobs(kind,item_id,platform,metric)
            SELECT v.kind,v.item_id,v.platform,m.metric
            FROM equipment_rank_scope_versions v
            JOIN (
                SELECT kind,item_id,platform,sum(population) population
                  FROM equipment_population GROUP BY 1,2,3
                UNION ALL
                SELECT kind,item_id,'all'::text,sum(population)
                  FROM equipment_population GROUP BY 1,2
            ) ep ON ep.kind=v.kind AND ep.item_id=v.item_id
                  AND ep.platform=v.platform
            CROSS JOIN LATERAL (
                SELECT unnest(CASE WHEN v.kind='weapon'
                  THEN ARRAY['kills','kpm','accuracy']::text[]
                  ELSE ARRAY['kills','kpm']::text[] END) metric
            ) m
            WHERE ep.population>0
            ON CONFLICT DO NOTHING
        """)).rowcount

def claim(engine, worker):
    with engine.begin() as c:
        capacity = c.execute(text("""
            SELECT max_active_builds,lease_seconds FROM equipment_rank_capacity
            WHERE id=1 FOR UPDATE
        """)).one()
        # Serialize both admission and reclamation through capacity row.
        active = c.execute(text("""
            SELECT count(*) FROM equipment_rank_jobs
            WHERE lease_expires_at > clock_timestamp()
        """)).scalar_one()
        if active >= capacity.max_active_builds:
            return None
        job = c.execute(text("""
            SELECT kind,item_id,platform,metric FROM equipment_rank_jobs
            WHERE next_due_at <= clock_timestamp()
              AND (lease_expires_at IS NULL OR lease_expires_at <= clock_timestamp())
            ORDER BY next_due_at,kind,item_id,platform,metric
            FOR UPDATE SKIP LOCKED LIMIT 1
        """)).mappings().first()
        if not job:
            return None
        token = uuid.uuid4()
        row = c.execute(text("""
            UPDATE equipment_rank_jobs
            SET claimed_by=:w,claim_token=:t,claim_epoch=claim_epoch+1,
                lease_expires_at=clock_timestamp()+make_interval(secs=>:seconds),
                attempts=attempts+1,updated_at=clock_timestamp()
            WHERE kind=:kind AND item_id=:item_id AND platform=:platform AND metric=:metric
            RETURNING claim_epoch
        """), dict(job,w=worker,t=token,seconds=capacity.lease_seconds)).one()
        return dict(job,worker_id=worker,token=token,epoch=row.claim_epoch)

def renew(engine, job):
    with engine.begin() as c:
        seconds = c.execute(text("SELECT lease_seconds FROM equipment_rank_capacity WHERE id=1")).scalar_one()
        return c.execute(text("""
            UPDATE equipment_rank_jobs
            SET lease_expires_at=clock_timestamp()+make_interval(secs=>:seconds),
                updated_at=clock_timestamp()
            WHERE kind=:kind AND item_id=:item_id AND platform=:platform AND metric=:metric
              AND claimed_by=:worker_id AND claim_token=:token AND claim_epoch=:epoch
              AND lease_expires_at>clock_timestamp()
        """), dict(job,seconds=seconds)).rowcount == 1

def finish(engine, job, success, error=None, refresh_seconds=3600):
    with engine.begin() as c:
        return c.execute(text("""
            UPDATE equipment_rank_jobs
            SET claimed_by=NULL,claim_token=NULL,lease_expires_at=NULL,
                last_success_at=CASE WHEN :ok THEN clock_timestamp() ELSE last_success_at END,
                last_error=:error,
                next_due_at=clock_timestamp()+make_interval(secs=>
                    CASE WHEN :ok THEN :refresh
                         ELSE least(3600, 30 * power(2, least(attempts,7)))::integer END),
                updated_at=clock_timestamp()
            WHERE kind=:kind AND item_id=:item_id AND platform=:platform AND metric=:metric
              AND claimed_by=:worker_id AND claim_token=:token AND claim_epoch=:epoch
              AND lease_expires_at>clock_timestamp()
        """), dict(job,ok=success,error=error,refresh=refresh_seconds)).rowcount == 1
