"""Exact-scope, capacity-fenced claim for a one-shot compact publication."""
import uuid
from sqlalchemy import text


def claim_scope(engine, worker, kind, item_id, platform, metric):
    key = dict(kind=kind, item_id=item_id, platform=platform, metric=metric)
    with engine.begin() as c:
        capacity = c.execute(text('''SELECT max_active_builds,lease_seconds
            FROM equipment_rank_capacity WHERE id=1 FOR UPDATE''')).one()
        if c.execute(text('SELECT current_database()')).scalar_one() == 'bf4_playerstats':
            if c.execute(text('SELECT public.bf4ps_rank_gate_ready()')).scalar_one() is not True:
                return None
        active = c.execute(text('''SELECT count(*) FROM equipment_rank_jobs
            WHERE lease_expires_at>clock_timestamp()''')).scalar_one()
        if active >= capacity.max_active_builds:
            return None
        job = c.execute(text('''SELECT 1 FROM equipment_rank_jobs
            WHERE kind=:kind AND item_id=:item_id AND platform=:platform AND metric=:metric
              AND (lease_expires_at IS NULL OR lease_expires_at<=clock_timestamp())
            FOR UPDATE SKIP LOCKED'''), key).first()
        if job is None:
            return None
        token = uuid.uuid4()
        epoch = c.execute(text('''UPDATE equipment_rank_jobs SET
            claimed_by=:worker,claim_token=:token,claim_epoch=claim_epoch+1,
            lease_expires_at=clock_timestamp()+make_interval(secs=>:seconds),
            attempts=attempts+1,updated_at=clock_timestamp()
            WHERE kind=:kind AND item_id=:item_id AND platform=:platform AND metric=:metric
            RETURNING claim_epoch'''),
            dict(key,worker=worker,token=token,seconds=capacity.lease_seconds)).scalar_one()
        return dict(key,worker_id=worker,token=token,epoch=epoch)
