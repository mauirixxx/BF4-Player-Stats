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
- `event_type` (for example `claimed`, `started`, `succeeded`, `failed`, `lease_expired`, `retry_scheduled`, `promoted`);
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

The high-level materialization and priority policies are now locked. Remaining implementation design includes:

- exact `collection_jobs` columns, indexes, state machine, claim query, and lease semantics;
- exact `collection_events` schema/indexes and retention cleanup mechanism;
- how progressive bootstrap materialization selects profile/weapons/vehicles work after initial detailed collection;
- active/recent time windows and fairness/aging weights;
- retry/backoff timings and classification;
- how the dedicated interactive collector and background collectors select/chain work without duplicate claims;
- ETA calculation for interactive requests;
- metrics and health surfaces derived from jobs/events/state.

These details should be settled before migration `0001` freezes the queue/event tables.
