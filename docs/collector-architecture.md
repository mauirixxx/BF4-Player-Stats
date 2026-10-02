# BF4PS Collector Architecture

This document records the collector/work-queue architecture decisions made during BF4PS design. It complements `docs/database-schema.md`. Queue-table details remain deliberately open until job-creation/materialization behavior is settled.

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

## Still open: when resource jobs are created

The next architecture decision is **job materialization**.

Two broad models remain under discussion:

1. **Eager materialization:** when a soldier becomes known, immediately create all four resource jobs (`detailed`, `profile`, `weapons`, `vehicles`) with different priorities/eligibility times.
2. **Demand/eligibility materialization:** keep `collection_state` as the durable source of truth and create/claim queue work only when a resource actually becomes eligible or is explicitly requested.

A hybrid is also possible—for example, eagerly materializing initial bootstrap work while generating later refresh jobs from collection state/activity events.

This decision must account for the existing 175k+ BF4SW seed population, ongoing BF4SW discoveries, active-player refreshes, post-activity finalization, 30-day profile checks, retries/backoff, manual high-priority full collections, duplicate/coalesced requests, queue observability, and crash/failover recovery.

Do not freeze the final queue table in migration `0001` until this behavior is settled and documented.
