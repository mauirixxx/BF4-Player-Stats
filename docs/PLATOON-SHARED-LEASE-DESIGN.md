# Shared per-platoon lease: deployment design

## Invariant

Exactly one active claim per platoon ID, regardless of whether the work originated from
a new request or a scheduled refresh. Every roster import verifies the same claim
inside its database transaction while holding a row lock. A stale worker must never
write roster rows, mark a request complete, or reschedule the platoon.

## Schema (migration, applied by schema owner, not collector)

```sql
CREATE TABLE platoon_work_leases (
  platoon_id bigint PRIMARY KEY,
  claim_token uuid NOT NULL,
  claimed_by text NOT NULL,
  lease_until timestamptz NOT NULL,
  claimed_at timestamptz NOT NULL DEFAULT now(),
  work_kind text NOT NULL CHECK (work_kind IN ('request','refresh'))
);
CREATE INDEX platoon_work_leases_expiry_idx ON platoon_work_leases (lease_until);
GRANT SELECT, INSERT, UPDATE, DELETE ON platoon_work_leases TO bf4ps_platoon_collector;
```

The claim token must be random and unique per acquisition. Reclaim an expired row
with atomic `INSERT ... ON CONFLICT DO UPDATE ... WHERE lease_until < now()
RETURNING claim_token`; a non-expired row is never overwritten. The claim
is acquired **before** selecting a request or refresh job for processing. Claim
and job-state transition must be in one transaction, or roll back together.

## Import and completion

Import transaction: lock `platoon_work_leases` row with `FOR UPDATE`, assert
platoon ID, token, and `lease_until > clock_timestamp()`, then write roster
snapshot. Request/refresh completion must check token in the same transaction,
release lease only after all dependent writes commit. Failure/retry must also
be token-fenced. Avoid stale worker writes to local shared artifacts.

## Rollout

1. Verify live schema and migration ownership.
2. Add isolated PostgreSQL tests: two simultaneous request/refresh acquisitions
   for the same ID; expired takeover; stale import rollback; current owner commit;
   failed claim must not mutate queue state.
3. Stop the mak-05 platoon timer briefly for migration and code cutover.
4. Apply migration, deploy the same commit to mak-05 and hnl-03.
5. Verify single-node smoke tests; enable hnl-03 only after all gates pass.
6. Monitor job throughput, errors, retries, leases, and Battlelog traffic.

Do not use the existing `next_refresh_at` or `last_attempt_at` timestamps
as the cross-queue lease authority; they belong to different scheduling paths.
