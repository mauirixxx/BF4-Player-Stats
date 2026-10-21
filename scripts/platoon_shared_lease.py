#!/usr/bin/env python3
"""SQL primitives for shared per-platoon ownership, request and refresh alike.

Call acquire() inside the same transaction as the queue-state transition.
All import/finalization transactions must lock and validate the same token.
"""
import uuid

def quote(value):
    return "'" + str(value).replace("'", "''") + "'"

def acquire(platoon_id, worker, kind, minutes=15, token=None):
    pid=int(platoon_id)
    if pid<=0 or kind not in ("request","refresh") or not 1<=minutes<=60:
        raise ValueError("invalid lease acquisition")
    token=str(uuid.UUID(str(token))) if token else str(uuid.uuid4())
    return f"""INSERT INTO platoon_work_leases
      (platoon_id,claim_token,claimed_by,lease_until,work_kind)
      VALUES ({pid},{quote(token)}::uuid,{quote(worker)},now()+interval '{minutes} minutes',{quote(kind)})
      ON CONFLICT (platoon_id) DO UPDATE SET
        claim_token=EXCLUDED.claim_token,claimed_by=EXCLUDED.claimed_by,
        lease_until=EXCLUDED.lease_until,claimed_at=now(),work_kind=EXCLUDED.work_kind
      WHERE platoon_work_leases.lease_until<now()
      RETURNING claim_token;"""

def guard(platoon_id, token):
    pid=int(platoon_id)
    token=str(uuid.UUID(str(token)))
    return (f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM platoon_work_leases "
            f"WHERE platoon_id={pid} AND claim_token={quote(token)}::uuid "
            "AND lease_until>clock_timestamp() FOR UPDATE) "
            "THEN RAISE EXCEPTION 'stale platoon claim'; END IF; END $$;")

def release(platoon_id, token):
    pid=int(platoon_id)
    token=str(uuid.UUID(str(token)))
    return (f"DELETE FROM platoon_work_leases WHERE platoon_id={pid} "
            f"AND claim_token={quote(token)}::uuid;")
