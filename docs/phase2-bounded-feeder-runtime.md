# BF4PS Phase 2 Bounded Feeder and Single-Node Runtime Design

This document freezes the next implementation boundary after the Phase 1 detailed collector acceptance work. It must be consulted before implementing the bounded feeder or long-running collector runtime.

It complements `docs/phase1-detailed-collector.md`, `docs/collector-architecture.md`, and `docs/database-schema.md`. Those documents remain authoritative for the queue, collection-state, statistics-retention, priority, and source-of-truth decisions already made.

## Why this is Phase 2

Phase 1 deliberately excluded automatic scheduling and used manually materialized jobs for a tiny validation cohort. Its acceptance contract says that only after the single-job collector behavior is proven should BF4PS implement the bounded bootstrap feeder and begin measuring sustained detailed-statistics throughput.

Phase 2 therefore does **not** begin by deploying the eight-node fleet. It first turns the proven detailed-statistics primitives into one conservative, restart-safe service on `tcou` against `bf4_playerstats_test`.

The purpose is to answer a new question: can BF4PS continuously materialize a small bounded amount of legitimate bootstrap work, consume it safely for an extended period, survive stop/restart, and produce useful throughput/throttle evidence without creating an unbounded Battlelog backlog or request storm?

## Phase 2 scope

Phase 2 implements only:

- a bounded background feeder for `resource='detailed'`;
- a single long-running background collector process on `tcou`;
- collector registration and liveness maintenance;
- graceful drain/shutdown behavior;
- conservative database-coordinated Battlelog request pacing;
- structured operational logging sufficient for a controlled soak;
- test-database validation and a deliberately bounded live cohort/working set.

Phase 2 does **not** yet implement:

- profile, weapon, or vehicle collection;
- the production 175k+ bootstrap run;
- eight-node deployment;
- the interactive/manual collector lane;
- production activity-aware refresh scheduling;
- final production request-rate constants;
- automatic rate increases;
- sophisticated fairness weights or resource watermarks;
- production service packaging/systemd/Docker deployment until the runtime behavior itself is validated.

## Durable backlog versus actionable queue

The existing architectural distinction is preserved:

- `collection_state` describes the durable state of the total known soldier population;
- `collection_jobs` contains only work that is actionable now.

The feeder must never eagerly create one detailed job for every known soldier. It maintains a bounded working set and replenishes only the deficit.

Conceptually:

```text
soldiers + collection_state
          |
          v
   bounded feeder
          |
          | replenish deficit only
          v
   collection_jobs
          |
          v
 single tcou collector
          |
          v
      Battlelog
```

No external `last soldier_id` bootstrap cursor is introduced. PostgreSQL state answers which soldiers remain unattempted/eligible, so stopping and restarting the feeder cannot lose the logical backlog.

## Initial Phase 2 eligibility

The first feeder implementation is intentionally narrower than the eventual production scheduler.

A soldier is eligible for Phase 2 bootstrap detailed work when:

1. the soldier exists in BF4PS with a supported platform;
2. its detailed collection state is `never_attempted` (or equivalently has never successfully/meaningfully been attempted according to the existing schema semantics);
3. there is no existing actionable `(soldier_id, 'detailed')` job;
4. it is inside the operator-selected Phase 2 test boundary.

Retryable jobs already returned to `pending` by the collector are **not** duplicated by the feeder. Their existing queue row and `eligible_at` remain authoritative.

Phase 2 does not yet materialize normal periodic refresh work for already-successful parked soldiers. That belongs to the later activity/freshness scheduler.

## Test boundary

The first continuous soak must not silently consume the entire imported BF4SW population merely because the database contains it.

The feeder therefore requires an explicit test limit/boundary for Phase 2. The implementation must support a hard maximum population or equivalent deterministic eligibility boundary that can be inspected before the process starts. The default for development must be safe/off rather than "all soldiers".

The initial operator run on `tcou` will use a deliberately small cohort/limit. Expansion happens manually after database and Battlelog behavior are inspected.

## Bounded working set

The feeder has a configurable target depth for background detailed jobs. The target counts actionable detailed/background rows across `pending`, `claimed`, and `running`; claimed/running work is still part of the working set and must not cause unnecessary replenishment.

On each feeder pass:

```text
deficit = target_depth - current_actionable_depth
```

If `deficit <= 0`, no jobs are created.

If a deficit exists, the feeder selects at most that many eligible soldiers and materializes at most one detailed job per soldier. The existing unique `(soldier_id, resource)` protection remains authoritative under races.

The Phase 2 default target is intentionally small and configurable. A development default of **10 actionable jobs** is appropriate for the first `tcou` soak; this is a test-runtime default, not a production architectural constant.

The feeder runs periodically rather than after every individual collection. An initial **5-second feeder interval** is acceptable for the tiny test working set and is configurable. It does not control Battlelog request rate; the request gate does.

## Initial ordering

For the Phase 2 never-attempted bootstrap subset, deterministic ordering is used so behavior is inspectable and restart-safe. Selection should use stable database ordering, initially oldest/lowest `soldier_id` among the allowed test boundary unless an explicit cohort mechanism supplies a different deterministic order.

This is **not** the final production priority scheduler. The already-designed interactive/active/recent/bootstrap fairness policy remains the production direction, but Phase 2 must not pretend those weights have been measured before sustained throughput exists.

Jobs created by this feeder use the existing background lane and bootstrap priority/reason semantics.

## Long-running collector loop

One process on `tcou` performs the following lifecycle:

```text
startup
  |
  +-> validate configuration/database
  +-> register or refresh stable collector identity
  +-> mark heartbeat healthy
  |
  v
loop
  |
  +-> refresh collector heartbeat/control state
  +-> if drained/disabled: do not claim new work; sleep
  +-> feeder pass when due
  +-> attempt to collect one eligible detailed/background job
  +-> if no job: idle sleep
  +-> repeat
  |
SIGTERM/SIGINT
  |
  +-> stop feeder/materialization
  +-> stop claiming new work
  +-> allow current synchronous collection transaction to finish when practical
  +-> update collector liveness/stopped state best-effort
  v
exit
```

The process owns at most one resource job at a time. It must not preclaim a batch.

The existing request gate remains the authority for outbound request start spacing. Loop speed, feeder cadence, and idle sleep must never bypass it.

## Stable collector identity

The runtime requires an explicit stable `collector_uuid`, collector name, hostname, lane, and `egress_key`. A random UUID generated on every process restart is not acceptable for the real runtime.

For the first `tcou` service, these values are supplied by configuration/environment and registered/refreshed in `collectors` on startup. Restarting the same configured service reuses its identity.

The runtime must reject obviously invalid/missing identity configuration rather than silently inventing a new production identity.

## Heartbeat and control state

The `collectors` row is the current control/liveness surface. The runtime periodically refreshes `last_heartbeat_at`, software version when available, and current health state.

The runtime also honors `enabled` and `drained`:

- `enabled=false`: do not claim/materialize work for this collector; remain quiescent or exit according to implementation policy;
- `drained=true`: finish any already-owned work but claim no new jobs;
- `drained=false` and `enabled=true`: normal operation.

Routine successful heartbeats do not append collection events. Only meaningful heartbeat-health transitions should eventually create operational events, consistent with the architecture contract.

For the first single-process soak, an initial **15-second heartbeat interval** is reasonable and configurable. It is an operational test value, not a schema constant.

## Lease behavior

The existing fenced lease primitives remain unchanged. A collector that crashes while owning a job strands at most that one job until lease expiry, after which another/restarted collector can reclaim it.

The runtime must not create a second ownership mechanism around the queue. PostgreSQL job ownership plus `lease_token` remains authoritative.

The initial detailed collector lease remains configurable. Phase 2 must choose a value comfortably above observed request/processing durations and any request-gate wait. It must not rely on the sub-second happy-path timings seen in Patient Zero as a permanent upper bound.

If later sustained testing shows a collection can legitimately approach lease expiry, lease renewal is used rather than weakening stale-owner fencing.

## Request pacing

The PostgreSQL request gate validated in Phase 1 remains mandatory before every Battlelog request.

The first continuous `tcou` soak uses a deliberately conservative configurable request interval. The runtime must never auto-tune upward based on successful requests.

Request rate changes are operator decisions backed by measured evidence. HTTP 403/throttle behavior is recorded and must trigger conservative retry behavior; BF4PS must not respond to throttling by increasing concurrency.

The Phase 2 soak is specifically intended to collect evidence for the eventual safe sustained detailed-statistics rate.

## Failure behavior

The Phase 1 atomic failure/recovery contract is reused unchanged:

- retryable Battlelog/source failures preserve last-known-good statistics;
- collection state and structured failure event are updated atomically with queue release/retry eligibility;
- arbitrary BF4PS/PostgreSQL/programming failures are not disguised as successful retry persistence;
- stale owners cannot finalize after lease loss;
- a retryable job already present in the queue is not duplicated by the feeder.

A process-level unexpected exception should be logged with enough context to diagnose it. The service may continue after a job-scoped known failure, but infrastructure/programming failures should fail loudly rather than entering a tight exception loop.

## Idle behavior

When no eligible job is available, the worker sleeps for a configurable short idle interval rather than busy-polling PostgreSQL. An initial **1-second idle sleep** is acceptable for the single-node test runtime.

The feeder cadence remains independent of idle sleep. A queue becoming empty does not authorize an unbounded feeder fill; only the configured target deficit is replenished.

## Graceful shutdown

SIGTERM and SIGINT initiate drain-like local shutdown:

1. stop scheduling feeder passes;
2. stop claiming new jobs;
3. if no job is in flight, exit promptly;
4. if a synchronous collection is already in flight, allow it to complete when practical;
5. update the collector registry best-effort before exit.

The process must not delete or fabricate queue state merely to make shutdown look clean. If the process dies abruptly, the existing lease-expiry recovery path is the safety mechanism.

Phase 2 should include a deliberate kill/restart test after ordinary graceful-shutdown behavior is proven.

## Observability for the soak

At minimum, human-readable runtime logs should expose:

- startup identity and database target (without credentials);
- feeder target/current depth and number materialized when a refill occurs;
- job ID, soldier/persona/platform, attempt, and result;
- collection duration and HTTP status when available;
- retry classification/backoff when applicable;
- drain/disable transitions;
- shutdown reason;
- unexpected exceptions.

The structured database event log remains the durable per-collection operational record. Process logs are not a replacement for `collection_events`.

For soak review, database queries must be able to summarize at least request count, success/failure count, HTTP 403 count, average/maximum duration, queue depth, never-attempted versus attempted coverage inside the test boundary, and stuck/expired ownership.

## Configuration surface

The first implementation should keep the runtime values explicit and environment-driven. Names may be adjusted to match existing project conventions, but the conceptual settings are:

```text
BF4PS_DATABASE_URL
BF4PS_COLLECTOR_UUID
BF4PS_COLLECTOR_NAME
BF4PS_COLLECTOR_LANE=background
BF4PS_EGRESS_KEY
BF4PS_REQUEST_INTERVAL_SECONDS
BF4PS_JOB_LEASE_SECONDS
BF4PS_HEARTBEAT_INTERVAL_SECONDS=15
BF4PS_IDLE_SLEEP_SECONDS=1
BF4PS_FEEDER_INTERVAL_SECONDS=5
BF4PS_FEEDER_TARGET_DEPTH=10
BF4PS_PHASE2_MAX_SOLDIERS / explicit test-boundary equivalent
```

The implementation must refuse unsafe ambiguity around the test boundary. There must be no accidental default that means "collect all imported soldiers."

## First live validation sequence

Implementation is accepted incrementally, not by immediately leaving the service unattended.

1. Unit-test feeder deficit calculation, eligibility, deduplication, stable ordering, and hard test-boundary enforcement.
2. Integration-test feeder materialization against `bf4_playerstats_test` without Battlelog traffic.
3. Start the runtime with collection disabled/drained and verify registration/heartbeat/control behavior.
4. Enable a tiny explicit cohort and allow a handful of real detailed collections.
5. Verify queue depth remains bounded and no duplicate jobs/history appear.
6. Test graceful SIGTERM and restart.
7. Test abrupt termination while work is owned, then validate lease-based recovery.
8. Run a short attended soak and inspect events, failures, 403s, durations, queue state, and database consistency.
9. Expand the test boundary only by explicit operator action.

Only after these checks are clean should we consider a longer unattended `tcou` soak or production/distributed deployment design.

## Phase 2 acceptance gate

Phase 2 single-node runtime is successful when live test-database validation proves:

- the feeder never exceeds its configured actionable working-set target except for legitimate pre-existing/promoted work accounted for by policy;
- repeated feeder passes do not create duplicate soldier/resource jobs;
- restart requires no fragile bootstrap cursor and resumes from PostgreSQL state;
- one collector continuously consumes detailed jobs through the proven request gate;
- graceful drain/shutdown stops new claims without corrupting owned work;
- abrupt death leaves at most one owned job and lease expiry makes it recoverable;
- retryable collection failures preserve last-good data and remain recoverable;
- unchanged recollections do not manufacture history;
- structured events and process logs are sufficient to explain observed behavior;
- the bounded test cohort shows no unexplained queue corruption, stuck work, or unsafe Battlelog behavior;
- automated tests remain green.

Only then should BF4PS enlarge the bootstrap population and use the measured evidence to design the distributed background deployment and production pacing.

## Explicit non-goals

This design intentionally does not freeze the final production working-set depth, sustained Battlelog rate, active/recent fairness weights, full-resource bootstrap mix, eight-node topology behavior, or interactive ETA policy. Those decisions require the evidence this Phase 2 runtime is intended to produce.
