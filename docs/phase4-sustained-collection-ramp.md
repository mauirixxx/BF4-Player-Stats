# BF4PS Phase 4 sustained collection ramp

Status: **DESIGN FROZEN — implementation/validation next**

Date: 2026-10-05 UTC

Predecessor: Phase 3E final acceptance **PASS**

Current Alembic head: `0003_request_gates`

## Purpose

Phase 4 transitions BF4PS from bounded lifecycle/failure validation into sustained distributed detailed-stat collection that intentionally grows the test database from multiple physical nodes.

The ramp has three ordered stages:

1. **Phase 4A — small sustained PC cohort**
2. **Phase 4B — large sustained PC cohort**
3. **Phase 4C — multi-platform sustained cohort**

The stages deliberately increase only one major risk dimension at a time. Phase 4A proves ordinary sustained operation after the Phase 3E harnesses. Phase 4B increases volume and duration while retaining one platform. Phase 4C adds platform diversity only after the larger single-platform run is clean.

This phase remains restricted to `bf4_playerstats_test` on `mak-db-02.bf4statusbot.com`. Production collection is out of scope.

## Authoritative implementation contracts

Implementation must continue to follow:

- `docs/database-schema-reference.md` plus the complete current Alembic chain before any schema-dependent code is written;
- `docs/collector-architecture.md` for one-soldier/one-resource work units, bounded materialization, leases, fencing, and PostgreSQL request gates;
- the production `bf4ps.bounded_feeder`, collector runtime, job ownership, detailed collector, failure handling, and persistence paths rather than Phase-4-specific SQL substitutes for production behavior.

No schema migration is currently required for Phase 4. If implementation discovers a schema requirement, stop, design the migration, and update the schema reference in the same change set.

## Frozen safety principles

### Detailed resource only

Phase 4 collects only `resource='detailed'`. Profile, weapons, and vehicles remain out of scope until sustained detailed collection is understood.

### Background lane only

All Phase 4 work uses the background lane. Interactive/manual work is not part of this ramp.

### Bounded feeder remains mandatory

The total backlog must never be eagerly copied into `collection_jobs`. `collection_state` remains the durable backlog and `collection_jobs` remains a bounded actionable working set.

Every Phase 4 feeder invocation must retain an explicit population boundary. An omitted/unbounded soldier boundary must remain a refusal condition.

### Production ownership path only

Collectors must use normal claim, lease-token, request-gate, persistence, event, finalization, and retry behavior. Successful work must not be manufactured with direct harness inserts into detailed current/history or event tables.

### Stable physical collectors

Initial Phase 4 distributed collection uses the already validated physical nodes:

- `hnl-01`
- `kah-01`
- `tcou`

Stable collector UUIDs and distinct egress identities are preserved. A later expansion toward the planned eight-node fleet is explicitly outside the small/large/multi acceptance ramp.

### Conservative pacing

Phase 4 starts with the already exercised detailed-request spacing of **5.0 seconds per independent egress gate**. The ramp is intended to measure sustainable behavior, not discover maximum possible request rate.

No stage may automatically increase request rate because the previous stage was successful. Faster pacing requires a separate evidence-backed decision.

### Stop conditions

A stage must stop feeding new work and be investigated if any of the following occurs:

- HTTP 403 or 429 / throttle-class evidence;
- unexpected foreign jobs or resources;
- ownership/fencing invariant failure;
- persistent database error;
- malformed/normalization failures suggesting a systemic source-shape change;
- queue growth materially beyond the configured bounded working set without a known transient explanation;
- collector identity or egress mismatch;
- target database/Alembic mismatch.

Ordinary isolated player-level unavailable/not-found/temporary failures do not automatically invalidate a stage; they must be recorded and reconciled according to production failure policy.

## Phase 4A — small sustained PC cohort

### Goal

Prove that all three physical collectors can run ordinary production detailed collection continuously against a fresh PC cohort after Phase 3E, while the bounded feeder repeatedly replenishes work and PostgreSQL accumulates real current/history/event data.

### Frozen scale

- platform: **PC only**;
- fresh cohort: **90 soldiers** total;
- feeder target depth: **6 actionable jobs**;
- collectors: **3**;
- request spacing: **5.0 seconds per egress**;
- maximum terminal attempts: bounded to the selected cohort and stage acceptance contract.

Ninety soldiers is intentionally larger than a one-pass harness but still small enough for exact per-soldier reconciliation.

### Acceptance

Phase 4A passes when:

- the exact 90-soldier cohort is frozen before writes;
- all materialized work belongs only to that cohort, PC, detailed/background;
- all three collectors successfully finalize work during the stage;
- feeder replenishment is observed repeatedly rather than only in one seed transaction;
- the cohort converges with no live jobs left for it;
- every soldier ends in a valid detailed collection state;
- successful soldiers have `detailed_stats_current` rows;
- detailed history/event growth is reconcilable to observed outcomes;
- no 403/429/throttle evidence is present;
- no stale ownership remains;
- final collector stop is clean.

The run report must record elapsed time, terminal attempts, successes/failures by class, per-collector completions, request-gate/HTTP evidence, current/history row growth, and maximum observed actionable queue depth.

## Phase 4B — large sustained PC cohort

### Entry condition

Phase 4A must be documented PASS before Phase 4B starts.

### Goal

Increase duration and database growth enough to expose behavior that a 90-soldier run may hide: queue replenishment over many cycles, history/current persistence at larger volume, collector distribution, retry behavior, database transaction stability, and sustained source pacing.

### Frozen scale

- platform: **PC only**;
- fresh cohort: **900 soldiers** total;
- feeder target depth: **24 actionable jobs**;
- collectors: **3**;
- request spacing: **5.0 seconds per egress**.

The 900-soldier cohort is an order-of-magnitude increase over 4A while remaining tiny relative to the discovered PC population. It is large enough to keep three collectors busy for a sustained interval without authorizing an uncontrolled bootstrap.

### Acceptance

Phase 4B requires the same correctness invariants as 4A plus:

- sustained bounded-feeder operation across the run;
- no monotonic unexplained live-queue growth;
- no collector monopolizes the entire workload while other healthy eligible collectors remain idle for the whole run;
- aggregate and per-collector throughput are recorded;
- database current/history/event growth is measured before and after;
- failure/retry counts and oldest outstanding cohort work are reported;
- the run ends fully reconcilable and cleanly stopped.

A 900-soldier run is not permission to materialize or collect the rest of the PC population.

## Phase 4C — multi-platform sustained cohort

### Entry condition

Phase 4B must be documented PASS before Phase 4C starts.

### Goal

Prove the same distributed production path across all supported BF4 platforms without changing pacing or ownership semantics.

### Frozen scale

- **150 PC soldiers**;
- **150 PS4 soldiers**;
- **150 Xbox One soldiers**;
- total: **450 soldiers**;
- feeder target depth: **18 actionable jobs**;
- collectors: **3**;
- request spacing: **5.0 seconds per egress**.

The cohort must be frozen explicitly before collection begins. Selection prefers `detailed_state='never_attempted'`, no existing detailed job, valid persona/platform identity, and exclusion of prior Phase 3 validation cohorts where practical.

### Scheduling requirement

The multi-platform cohort must not accidentally become PC-only because of ascending global `soldier_id` order. The Phase 4C feeder/driver must deliberately preserve platform representation in the actionable working set or feed explicit platform-balanced subcohorts while still using normal production job materialization and collection semantics.

### Acceptance

Phase 4C passes when:

- all three exact 150-soldier platform cohorts are frozen and reconciled;
- all materialized jobs belong to the authorized 450 soldiers;
- each platform produces successful durable detailed collections;
- platform-specific failures are reported separately;
- no platform is silently starved by feeder ordering;
- all three physical collectors participate;
- no 403/429/throttle evidence appears;
- current/history/event growth reconciles across all platforms;
- no authorized cohort jobs remain live at closure;
- all collectors stop cleanly.

## Telemetry and evidence required for every stage

Each stage must preserve enough evidence to answer:

- exact cohort and platform counts;
- starting and ending collection-state distribution;
- actionable queue depth over time, including maximum observed depth;
- feeder passes and jobs materialized per pass;
- terminal event count and event-ID span;
- successes and failures by error class / HTTP status;
- completions by collector and egress identity;
- elapsed wall-clock time and aggregate throughput;
- `detailed_stats_current` row growth;
- `detailed_stats_history` row growth;
- whether history was appended versus current-only refreshed;
- residual queue ownership at closure;
- throttle evidence;
- clean-stop state.

The evidence scripts may be read-only reconciliation tools, but collection itself must continue through production paths.

## What Phase 4 does not prove

Passing 4A/4B/4C does not yet authorize:

- unrestricted collection of every discovered soldier;
- all eight planned background collectors;
- profile/weapons/vehicles bootstrap;
- interactive/manual lane production service;
- faster request pacing;
- production database cutover;
- final steady-state freshness scheduling.

Those require later staged decisions using Phase 4 throughput and failure evidence.

## Execution order

The order is frozen:

```text
Phase 3E final acceptance PASS
        |
        v
4A preflight/census -> freeze 90 PC -> sustained run -> reconcile -> document PASS
        |
        v
4B preflight/census -> freeze 900 PC -> sustained run -> reconcile -> document PASS
        |
        v
4C preflight/census -> freeze 150 PC + 150 PS4 + 150 Xbox One
                    -> sustained balanced run -> reconcile -> document PASS
        |
        v
Phase 4 acceptance / next-scale decision
```

Do not begin a later stage while the preceding stage has unresolved queue ownership, unexplained persistence differences, or undocumented acceptance gaps.
