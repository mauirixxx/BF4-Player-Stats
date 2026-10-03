# BF4PS Operational PostgreSQL Schema v1

This document freezes the v1 operational tables that support distributed collection. It complements `database-schema.md`, `collector-architecture.md`, and `collector-registry.md` and is the implementation contract for migration `0001`.

## Design rules

- PostgreSQL is the coordination authority.
- Collector UUID is the durable collector incarnation identity; collector name is operator-facing.
- A collector normally owns at most one live resource job.
- A live resource job is one `(soldier, resource)` work unit.
- There may be at most one actionable job for a `(soldier_id, resource)` pair.
- Lease tokens protect claims from stale/zombie collectors, including stale processes from the same collector UUID.
- `collection_jobs` is a bounded actionable working set, not the total backlog.
- `collection_state` is the durable total backlog/freshness truth.
- `collection_events` is append-only operational history and never stores Battlelog response bodies.
- Failures never erase last-known-good gameplay statistics.

## PostgreSQL prerequisites

Migration `0001` enables `pgcrypto` so PostgreSQL can generate UUID values with `gen_random_uuid()`.

## collectors

Current registry and liveness state for each collector incarnation.

```sql
CREATE TABLE collectors (
    collector_uuid uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    collector_name text NOT NULL,
    hostname text NOT NULL,
    lane text NOT NULL,
    egress_key text NOT NULL,
    enabled boolean NOT NULL DEFAULT true,
    drained boolean NOT NULL DEFAULT false,
    software_version text,
    started_at timestamptz,
    last_heartbeat_at timestamptz,
    heartbeat_state text NOT NULL DEFAULT 'unknown',
    heartbeat_lost_at timestamptz,
    current_job_id bigint,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    retired_at timestamptz,

    CONSTRAINT collectors_name_nonempty CHECK (btrim(collector_name) <> ''),
    CONSTRAINT collectors_hostname_nonempty CHECK (btrim(hostname) <> ''),
    CONSTRAINT collectors_egress_nonempty CHECK (btrim(egress_key) <> ''),
    CONSTRAINT collectors_lane_check CHECK (lane IN ('background', 'interactive')),
    CONSTRAINT collectors_heartbeat_state_check
        CHECK (heartbeat_state IN ('unknown', 'healthy', 'lost'))
);

CREATE UNIQUE INDEX uq_collectors_active_name
    ON collectors (lower(collector_name))
    WHERE retired_at IS NULL;

CREATE INDEX ix_collectors_heartbeat
    ON collectors (heartbeat_state, last_heartbeat_at)
    WHERE retired_at IS NULL;

CREATE INDEX ix_collectors_egress
    ON collectors (egress_key)
    WHERE retired_at IS NULL;
```

A retired collector name may later be reused by a replacement incarnation with a new UUID. Historical events remain attached to the old UUID.

`current_job_id` receives its foreign key after `collection_jobs` exists, avoiding a table-creation cycle.

## collection_jobs

Small live/actionable queue. Successful/terminal history does not accumulate here.

```sql
CREATE TABLE collection_jobs (
    job_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    soldier_id bigint NOT NULL
        REFERENCES soldiers(soldier_id) ON DELETE CASCADE,
    resource text NOT NULL,
    lane text NOT NULL,
    priority_class text NOT NULL,
    reason text NOT NULL,
    status text NOT NULL DEFAULT 'pending',
    priority_value integer NOT NULL DEFAULT 0,
    eligible_at timestamptz NOT NULL DEFAULT now(),
    attempt_count integer NOT NULL DEFAULT 0,

    collector_uuid uuid
        REFERENCES collectors(collector_uuid) ON DELETE SET NULL,
    lease_token uuid,
    claimed_at timestamptz,
    started_at timestamptz,
    lease_expires_at timestamptz,

    last_error_class text,
    last_error_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT collection_jobs_resource_check
        CHECK (resource IN ('detailed', 'profile', 'weapons', 'vehicles')),
    CONSTRAINT collection_jobs_lane_check
        CHECK (lane IN ('background', 'interactive')),
    CONSTRAINT collection_jobs_priority_class_check
        CHECK (priority_class IN ('interactive', 'active', 'recent', 'bootstrap')),
    CONSTRAINT collection_jobs_status_check
        CHECK (status IN ('pending', 'claimed', 'running')),
    CONSTRAINT collection_jobs_attempt_count_check CHECK (attempt_count >= 0),
    CONSTRAINT collection_jobs_lease_shape_check CHECK (
        (status = 'pending'
            AND collector_uuid IS NULL
            AND lease_token IS NULL
            AND claimed_at IS NULL
            AND started_at IS NULL
            AND lease_expires_at IS NULL)
        OR
        (status = 'claimed'
            AND collector_uuid IS NOT NULL
            AND lease_token IS NOT NULL
            AND claimed_at IS NOT NULL
            AND started_at IS NULL
            AND lease_expires_at IS NOT NULL)
        OR
        (status = 'running'
            AND collector_uuid IS NOT NULL
            AND lease_token IS NOT NULL
            AND claimed_at IS NOT NULL
            AND started_at IS NOT NULL
            AND lease_expires_at IS NOT NULL)
    )
);

-- Every row in this table is actionable/live, so a normal unique constraint is
-- sufficient to coalesce duplicate demand.
ALTER TABLE collection_jobs
    ADD CONSTRAINT uq_collection_jobs_soldier_resource
    UNIQUE (soldier_id, resource);

CREATE INDEX ix_collection_jobs_claim
    ON collection_jobs
       (lane, priority_class, priority_value DESC, eligible_at, created_at, job_id)
    WHERE status = 'pending';

CREATE INDEX ix_collection_jobs_expired_lease
    ON collection_jobs (lease_expires_at, job_id)
    WHERE status IN ('claimed', 'running');

CREATE INDEX ix_collection_jobs_collector
    ON collection_jobs (collector_uuid)
    WHERE collector_uuid IS NOT NULL;

ALTER TABLE collectors
    ADD CONSTRAINT fk_collectors_current_job
    FOREIGN KEY (current_job_id)
    REFERENCES collection_jobs(job_id)
    ON DELETE SET NULL;
```

The queue contains no `succeeded` or permanent `failed` status. Final outcome is committed to durable collection state and append-only events; the actionable row is then removed atomically.

## collection_events

Append-only troubleshooting/audit history. Events snapshot useful external/operator identity values so historical display remains useful even if names/configuration later change.

```sql
CREATE TABLE collection_events (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    occurred_at timestamptz NOT NULL DEFAULT now(),

    collector_uuid uuid
        REFERENCES collectors(collector_uuid) ON DELETE SET NULL,
    collector_name_snapshot text,
    hostname_snapshot text,
    egress_key_snapshot text,

    job_id bigint,
    soldier_id bigint
        REFERENCES soldiers(soldier_id) ON DELETE SET NULL,
    persona_id bigint,
    platform text,
    resource text,
    lane text,
    event_type text NOT NULL,
    attempt_number integer,

    result text,
    duration_ms bigint,
    http_status integer,
    error_class text,
    error_message text,
    lease_token uuid,
    metadata jsonb,

    CONSTRAINT collection_events_resource_check
        CHECK (resource IS NULL OR resource IN ('detailed', 'profile', 'weapons', 'vehicles')),
    CONSTRAINT collection_events_lane_check
        CHECK (lane IS NULL OR lane IN ('background', 'interactive')),
    CONSTRAINT collection_events_platform_check
        CHECK (platform IS NULL OR platform IN ('pc', 'ps4', 'xboxone')),
    CONSTRAINT collection_events_attempt_check
        CHECK (attempt_number IS NULL OR attempt_number >= 0),
    CONSTRAINT collection_events_duration_check
        CHECK (duration_ms IS NULL OR duration_ms >= 0),
    CONSTRAINT collection_events_http_status_check
        CHECK (http_status IS NULL OR http_status BETWEEN 100 AND 599),
    CONSTRAINT collection_events_event_type_nonempty
        CHECK (btrim(event_type) <> '')
);

CREATE INDEX ix_collection_events_time
    ON collection_events (occurred_at DESC);

CREATE INDEX ix_collection_events_collector_time
    ON collection_events (collector_uuid, occurred_at DESC);

CREATE INDEX ix_collection_events_soldier_time
    ON collection_events (soldier_id, occurred_at DESC)
    WHERE soldier_id IS NOT NULL;

CREATE INDEX ix_collection_events_persona_time
    ON collection_events (platform, persona_id, occurred_at DESC)
    WHERE persona_id IS NOT NULL;

CREATE INDEX ix_collection_events_job
    ON collection_events (job_id, occurred_at)
    WHERE job_id IS NOT NULL;

CREATE INDEX ix_collection_events_type_time
    ON collection_events (event_type, occurred_at DESC);

CREATE INDEX ix_collection_events_http_errors
    ON collection_events (http_status, occurred_at DESC)
    WHERE http_status IS NOT NULL;
```

`job_id` deliberately has no foreign key because live jobs are deleted after finalization while their events must remain. `metadata` is for small structured operational context only; it must never contain raw Battlelog response bodies.

Expected event types include `created`, `promoted`, `claimed`, `started`, `succeeded`, `failed`, `retry_scheduled`, `lease_expired`, `reclaimed`, `heartbeat_lost`, and `heartbeat_restored`. Event type remains text rather than a PostgreSQL enum so future operational event types do not require an enum migration.

## Atomic claim contract

The queue is designed for PostgreSQL `FOR UPDATE SKIP LOCKED`. A collector should wait for its egress gate before claiming when practical, then claim one job atomically.

Representative claim shape:

```sql
WITH candidate AS (
    SELECT job_id
    FROM collection_jobs
    WHERE status = 'pending'
      AND lane = $1
      AND eligible_at <= now()
    ORDER BY
      CASE priority_class
        WHEN 'interactive' THEN 1
        WHEN 'active' THEN 2
        WHEN 'recent' THEN 3
        WHEN 'bootstrap' THEN 4
      END,
      priority_value DESC,
      eligible_at,
      created_at,
      job_id
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE collection_jobs AS j
SET status = 'claimed',
    collector_uuid = $2,
    lease_token = $3,
    claimed_at = now(),
    lease_expires_at = now() + $4::interval,
    attempt_count = attempt_count + 1,
    updated_at = now()
FROM candidate
WHERE j.job_id = candidate.job_id
RETURNING j.*;
```

Exact lease interval remains runtime configuration determined by endpoint measurements.

After claim, `collectors.current_job_id` and the `claimed` event are updated in the same transaction where practical.

## Start and lease ownership

Transitioning `claimed -> running`, renewing a lease, and finalizing a job must match all of:

```text
job_id
collector_uuid
lease_token
```

A stale process that no longer owns the current lease therefore cannot commit results merely because it has the same human collector name or even the same collector UUID.

Representative start guard:

```sql
UPDATE collection_jobs
SET status = 'running',
    started_at = now(),
    updated_at = now()
WHERE job_id = $1
  AND status = 'claimed'
  AND collector_uuid = $2
  AND lease_token = $3
  AND lease_expires_at > now()
RETURNING *;
```

Zero rows returned means ownership is no longer valid and the collector must not finalize that attempt.

## Expired lease recovery

A recovery transaction selects expired `claimed`/`running` jobs with row locking, records `lease_expired`/`reclaimed` events, and returns them to a valid pending shape by clearing collector/lease/start fields. Repeated recovery workers are safe when they use `FOR UPDATE SKIP LOCKED` or equivalent row locking.

A reclaimed job retains its accumulated `attempt_count`; retry/backoff policy may adjust `eligible_at` before it becomes claimable again.

## Successful finalization contract

Successful normalized collection finalization is one transaction:

1. verify `(job_id, collector_uuid, lease_token)` still owns an unexpired lease;
2. write/update the normalized authoritative current resource data;
3. append detailed-history state when the detailed snapshot rule says it changed;
4. update the resource's durable `collection_state` success/freshness fields;
5. append a structured `succeeded` event;
6. clear `collectors.current_job_id` if it still references this job;
7. delete the live `collection_jobs` row;
8. commit.

If the transaction fails, no partial successful finalization becomes visible and the existing leased job can later be recovered.

## Failure finalization contract

A failure transaction also verifies lease ownership. It records the structured failure event and updates durable `collection_state` without deleting last-known-good gameplay data.

- Retryable failures set the resource state/backoff/next attempt and either return/recreate actionable work according to scheduler policy.
- Meaningful terminal/unavailable results update durable state and remove the live job.
- Transport/parser/infrastructure failures must never masquerade as a legitimate zero/empty Battlelog result.

## Heartbeat contract

Routine collector heartbeat updates belong in `collectors.last_heartbeat_at` and current health state and do not create event spam.

Only health transitions are append-only events:

```text
healthy -> lost      => heartbeat_lost once
lost -> healthy      => heartbeat_restored once
```

`heartbeat_lost_at` provides the current outage boundary for operator displays. On restoration it may be cleared after the restoration event records the historical boundary.

These transitions measure observed BF4PS collector availability, not authoritative physical-host power uptime.

## Retention

`collection_events` begins with a 180-day operational retention target during bootstrap. Retention later becomes configurable and may be reduced after bootstrap/soak. Cleanup applies only to operational events and never gameplay/stat history.

## Values deliberately not frozen in migration 0001

The following remain runtime configuration/tuning rather than schema constants:

- lease duration;
- heartbeat interval and lost threshold;
- maximum claim-to-start delay;
- working-set target depth;
- feeder replenishment cadence;
- resource weights/watermarks;
- active/recent windows;
- fairness/aging weights;
- retry/backoff intervals;
- interactive ETA calculation;
- safe per-egress Battlelog request rates.
