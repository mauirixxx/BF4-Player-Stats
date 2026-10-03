# BF4PS Collector Architecture

This document records the collector/work-queue architecture decisions made during BF4PS design. It complements `docs/database-schema.md`.

## Confirmed work-unit model

The database work unit is **one soldier + one resource**.

Initial resource types are:

- `detailed`
- `profile`
- `weapons`
- `vehicles`

A collector claims an individual resource job rather than claiming an entire soldier as an indivisible all-resources operation. This keeps failure/retry scope small, allows resource-specific priorities and pacing, and supports the staged BF4SW bootstrap where detailed statistics are favored before the more expensive resources.

## Collector chaining

Although the durable work unit is one soldier/resource pair, a collector **may opportunistically chain additional eligible resources for the same soldier** when policy permits.

Examples:

- During the large BF4SW bootstrap, a collector that finishes `Player_X / detailed` will normally return to higher-priority queue work rather than automatically downloading Player_X's profile, weapons, and vehicles.
- For a manual/interactive full collection, after `Player_X / detailed` succeeds the collector may continue with the other eligible high-priority resources for Player_X, subject to the rate gate and queue policy.

Successful resources are committed independently. Failure of one resource must not invalidate successful collection of another resource or erase last-known-good data.

## Job materialization policy

`collection_state` is the durable source of truth. `collection_jobs` represents **actionable work**, not a permanent four-row shadow of every soldier.

For a newly discovered BF4SW soldier, BF4PS creates/updates the identity and provenance records, initializes collection state, and makes the initial `detailed` resource actionable. The remaining bootstrap resources are progressively materialized as policy/capacity permits rather than eagerly creating four permanent jobs for every member of the initial 175k+ population.

For a valid manual/interactive submission, all missing or sufficiently stale resources needed for the requested full collection (`detailed`, `profile`, `weapons`, `vehicles`) become high-priority interactive work immediately.

Steady-state refresh jobs are materialized when a resource becomes eligible because of activity/freshness policy, due time, retry/backoff expiry, or an explicit request. A parked/current inactive soldier has no dormant gameplay job merely waiting in the live queue.

At most one actionable job may exist for a `(soldier_id, resource)` pair. Repeated demand is coalesced. If equivalent background work already exists and a manual/interactive request arrives, BF4PS promotes the existing work rather than creating duplicate Battlelog traffic.

Completed/failed execution history is not represented by keeping completed jobs forever in the live queue; operational history is recorded separately in `collection_events`.

## Background lane

The preferred background architecture is **eight distributed BF4PS collectors running 24/7 on the existing eight BF4SW worker nodes**, in BF4PS's own Docker image/processes.

These collectors service background/bootstrap/scheduled work. PostgreSQL provides coordination and claiming/leases so that a logical resource job is owned by only one collector at a time and abandoned work can be recovered after lease expiry.

Sharing hosts with BF4SW is conditional on resource isolation and testing. BF4SW production monitoring has priority and BF4PS must not materially degrade it.

## Interactive lane

Manual website submissions use a **dedicated interactive collector lane/egress** rather than competing normally with the large background bootstrap backlog.

The website enqueues/coalesces work; it does not synchronously scrape Battlelog in the HTTP request. The interactive collector services full manual collection as soon as technically practical after current in-flight work, while still obeying Battlelog rate limits.

When interactive demand exceeds safe Battlelog capacity, requests remain queued. The website should eventually show a best-effort estimated attempt time based on measured throughput and the work ahead of the request. Exact wording and ETA calculation are deferred until real collector throughput is measured.

## Rate limiting and egress

Battlelog's rate limiting is treated as **egress-IP based**, based on prior BF4SW operational testing. BF4PS therefore treats the egress IP/rate-gate identity—not merely process count—as the scaling unit.

Conceptually:

```text
worker/collector A -> egress IP A -> rate gate A
worker/collector B -> egress IP B -> rate gate B
...
```

Collectors sharing an egress IP must share that IP's request budget. Adding another process behind an existing egress does not imply additional Battlelog capacity. Independent egress IPs may provide additional safe capacity, subject to conservative measured limits.

BF4PS must still perform its own endpoint/rate reconnaissance before production scaling. Exact BF4SW rate constants are not copied blindly into BF4PS because stats endpoints and payload sizes differ from BF4SW's workload.

## Priority classes and fairness

Eligibility and priority are separate decisions:

- **eligibility** asks whether a resource actually needs collection;
- **priority** asks which eligible work should run first.

BF4SW `last_seen`/activity information influences background priority but does not override freshness rules. For example, an actively observed soldier whose detailed stats were successfully refreshed less than 60 minutes ago is not eligible merely because the player remains active.

Initial scheduling uses priority classes with FIFO ordering inside each class rather than a global `ORDER BY last_seen DESC`.

Conceptual classes, highest first:

1. **interactive** — explicit manual/user-requested work;
2. **active** — eligible resources for soldiers currently or very recently observed by BF4SW;
3. **recent** — eligible resources for recently observed soldiers;
4. **bootstrap** — older initial/background population.

Exact active/recent time windows and numeric weights are intentionally deferred until collector throughput and BF4SW activity integration are measured.

Pure `last_seen DESC` scheduling is rejected because continuously active/new players could indefinitely starve the old bootstrap. Pure global FIFO is also rejected because it would ignore useful evidence that a recently active soldier is more immediately relevant than an old never-returned bootstrap identity.

The scheduler must include aging/weighted fairness so lower-priority bootstrap work continues to drain even under sustained active/recent demand. Exact weights are operational tuning, not schema semantics. The dedicated interactive lane further isolates human-requested work from the background bootstrap.

## Structured collector event log

Collector actions are recorded from day one in an **append-only structured database event log** for troubleshooting and operational analysis. Do not store only preformatted prose messages; human-readable messages are generated from structured fields when displayed.

The table is conceptually `collection_events` and should include enough information to reconstruct what a collector did, including fields such as:

- `event_id`;
- `occurred_at timestamptz` (UTC);
- stable `collector_id` / worker identity;
- `job_id` when applicable;
- `soldier_id`;
- `persona_id`;
- `platform`;
- `resource` (`detailed`, `profile`, `weapons`, `vehicles`);
- `event_type` (for example `created`, `promoted`, `claimed`, `started`, `succeeded`, `failed`, `retry_scheduled`, `lease_expired`, `reclaimed`, `heartbeat_lost`, `heartbeat_restored`);
- attempt number;
- result/status;
- request/operation duration where applicable;
- HTTP status where applicable;
- error class and concise error message where applicable.

Persona ID + platform are retained in the event because they are stable external identity values useful during troubleshooting; current player name can be joined for presentation and must not be the audit identity.

The event log records **what BF4PS collectors do**, not raw Battlelog payload bodies. In particular, large weapons/vehicles JSON responses must never be copied into this log.

Useful queries should include: history for one persona/resource, actions by one collector, HTTP 403/rate-limit events by collector/egress, average resource duration, lease recovery, failures by endpoint/resource, and events within a UTC time window.

Retention is configurable. During the initial seed/bootstrap, the starting operational target is **180 days** so long-running bootstrap behavior can be investigated retrospectively. After the initial seed is complete and steady-state behavior is understood, the normal retention target may be reduced substantially (for example 30 days or 14 days). The final steady-state value is an operational configuration decision, not hard-coded schema behavior.

Retention cleanup must never delete gameplay/stat history; it applies only to collector operational events after their configured retention horizon.

## Job state machine and leases

The live job lifecycle is intentionally small. `collection_jobs` contains actionable work with states such as `pending`, `claimed`, and `running`. Success/failure outcomes are written to `collection_state` and `collection_events`; successful jobs do not remain forever as completed rows in the live queue.

A retryable failure updates durable collection state and makes/re-makes work eligible at `next_attempt_at` according to retry/backoff policy. Terminal/unavailable conditions are represented by collection state rather than immortal failed queue rows.

Claims must be atomic and safe across all distributed collectors. The intended PostgreSQL implementation uses row locking such as `FOR UPDATE SKIP LOCKED` (or an equivalent atomic claim operation) so concurrent collectors cannot claim the same resource job.

A claim records at least:

- stable `collector_id`;
- `claimed_at`;
- `lease_expires_at`;
- a unique `lease_token` (UUID or equivalent).

The lease token is required to prevent a stale/zombie collector from finalizing a job after its lease expired and another collector reclaimed it. Any state-changing completion/finalization must verify current lease ownership, not merely collector name.

If a collector disappears while holding work, the job remains unavailable until its lease expires. After expiry it becomes reclaimable. Reclamation is recorded as meaningful operational history. A dead collector should normally strand at most one Battlelog resource job, because collectors should not hoard batches of claimed jobs.

Successful finalization should be atomic: parsed authoritative stats/current-state writes, collection-state updates, the success event, and removal/completion of the live actionable job must commit together. A crash before commit therefore leaves the old job reclaimable rather than producing partially finalized state.

`claimed` and `running` remain distinguishable so BF4PS can measure time spent waiting after claim (for example at an egress rate gate) separately from the actual Battlelog request/processing duration.

The conceptual `collection_jobs` row includes fields such as:

- job ID;
- `soldier_id`;
- resource;
- lane/workload class;
- priority class / ordering value;
- live status;
- `eligible_at`;
- attempt count;
- `collector_id`;
- `lease_token`;
- `claimed_at`;
- `started_at`;
- `lease_expires_at`;
- creation/update timestamps;
- last error class/time as useful live-queue diagnostics;
- reason/source for the work (for example `bootstrap`, `bf4sw_discovery`, `active_refresh`, `final_refresh`, `scheduled_profile`, `manual`, `retry`).

Exact SQL types/indexes remain to be frozen in migration `0001` after the remaining scheduling semantics are settled.

## Collector liveness / heartbeat logging

Lease heartbeat/renewal traffic is **not logged on every successful heartbeat**. Routine successful heartbeats update current liveness/lease state only; logging each renewal would create high-volume operational noise without adding useful troubleshooting history.

BF4PS will, however, record **state transitions in heartbeat health**:

- the first transition from healthy to failed/missed heartbeat is logged once as `heartbeat_lost` (or equivalent);
- repeated failures while already in the failed state are not repeatedly logged;
- the first subsequent successful renewal/heartbeat is logged once as `heartbeat_restored`;
- ordinary successful heartbeats after restoration remain unlogged.

This provides useful outage/recovery boundaries without heartbeat spam and can support approximate collector-availability/troubleshooting timelines.

Heartbeat-transition events are operational evidence, not the authoritative source for exact node uptime. A collector process may be alive while database/network heartbeat delivery fails, and a host-level outage may require infrastructure monitoring to establish exact machine uptime. If exact node uptime becomes a requirement, BF4PS should expose/use a dedicated collector-health table/metric rather than deriving it solely from collection events.

## Collector claim behavior around the rate gate

A collector should generally own **one Battlelog resource job at a time**. It must not claim large batches and hold them while waiting for its egress rate gate.

Prefer waiting until the collector's egress gate indicates it can service another request reasonably soon before claiming the next job. This keeps leases meaningful, minimizes stranded work after collector failure, prevents queue hoarding, and makes interactive queue/ETA estimates more representative of actual service order.

If a claimed job must wait briefly at the rate gate, its `claimed` state captures that delay. Once Battlelog work actually begins it transitions to `running`.

Exact lease duration, heartbeat/renewal interval, and the maximum acceptable claim-to-start delay remain operational values to determine from measured detailed/profile/weapons/vehicles request durations and failure behavior. They must be configurable rather than hard-coded into schema semantics.

## Retry/failure classification

Failures are classified rather than treated identically. At minimum the implementation must be able to distinguish categories such as:

- Battlelog rate-limit/throttle response (including observed 403/other relevant responses);
- timeout/connection/network failure;
- Battlelog HTTP 5xx/transient service failure;
- meaningful not-found/unavailable identity/resource response;
- malformed/parse/schema failure;
- BF4PS/PostgreSQL/infrastructure failure.

Retryable failures schedule later eligibility with backoff. Exact retry intervals are deliberately deferred until Battlelog behavior is measured. Failures never erase last-known-good statistics.

## Coordination and failure behavior

Confirmed direction:

```text
DATABASE WORK UNIT
    = one soldier + one resource

COLLECTOR BEHAVIOR
    = may chain additional eligible resources
      for the same soldier

BACKGROUND LANE
    = 8 distributed 24/7 collectors
      across the BF4SW worker fleet

INTERACTIVE LANE
    = dedicated collector/egress
      full manual collection
      high priority

RATE LIMITING
    = per egress IP

COORDINATION
    = PostgreSQL claims + leases

FAILURE SCOPE
    = individual resource

SUCCESS
    = committed independently per resource
```

Collectors need stable worker identities, lease expiry/recovery, graceful drain/upgrade behavior, retry/backoff, and observability for queue depth, throughput, backlog age, failures, and rate-gate behavior.

## Remaining queue/scheduler design work

The high-level materialization, priority, lease, liveness-event, and claim policies are now locked. Remaining implementation design includes:

- exact `collection_jobs` SQL columns, indexes, constraints, and atomic claim query;
- exact `collection_events` SQL schema/indexes and retention cleanup mechanism;
- exact lease duration and heartbeat/renewal timing after measuring endpoint duration;
- how progressive bootstrap materialization selects profile/weapons/vehicles work after initial detailed collection;
- active/recent time windows and fairness/aging weights;
- retry/backoff timings and classification details;
- how the dedicated interactive collector and background collectors select/chain work without duplicate claims;
- ETA calculation for interactive requests;
- metrics and health surfaces derived from jobs/events/state.

These details should be settled before migration `0001` freezes the queue/event tables.
