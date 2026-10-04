# BF4PS Phase 1 Detailed Collector Contract

This document freezes the implementation contract for the first executable BF4PS Battlelog collector. It complements `docs/battlelog-data-sources.md`, `docs/collector-architecture.md`, and `docs/database-schema.md`; those documents remain authoritative for the broader architecture and retained statistics contract.

## Purpose

Phase 1 is a deliberately small Patient Zero implementation. Its job is to prove that BF4PS can safely claim one detailed-statistics job, fetch the authoritative Battlelog payload, normalize it, commit current/history/state/event data atomically, and recover correctly from failure before any large bootstrap feeder or distributed collector fleet is enabled.

## Scope

Phase 1 collects only the `detailed` resource using the anonymously accessible Battlelog endpoint:

```text
/bf4/warsawdetailedstatspopulate/{persona_id}/{platformInt}/
```

Supported platform mapping is:

| BF4PS platform | Battlelog platformInt |
| --- | ---: |
| `pc` | 1 |
| `ps4` | 32 |
| `xboxone` | 64 |

The first live collector runs on `tcou` against the BF4PS test database. It services one job at a time. Jobs are initially inserted manually for a tiny validation cohort; no automatic 175k+ bootstrap feeder is part of Phase 1.

Profile, weapon, and vehicle collection; the distributed eight-worker background fleet; the dedicated interactive lane; automatic scheduling; and production throughput tuning are explicitly deferred.

## Authoritative source and retained fields

Battlelog is the authoritative source for gameplay statistics. BF4SW supplies soldier discovery/activity, not statistics.

Normalization must implement the existing **Detailed Stats Retention Contract v1** in `docs/battlelog-data-sources.md`. Phase 1 does not invent additional retained fields. The retained raw contract includes rank, time played, multiplayer score fields, supported game-mode scores, general counters, team/objective counters, and the documented extra counters. Deterministic K/D, KPM, SPM, accuracy, and similar ratios remain derived values and are not persisted as authoritative counters.

Battlelog source types are not trusted blindly. Numeric normalization must be explicit and reject or classify malformed values rather than silently corrupting stored statistics.

## Raw payload policy

The normalized relational schema remains the authoritative BF4PS data model. Phase 1 must not make raw Battlelog JSON the primary statistics store and must not copy payload bodies into `collection_events`.

During collector development, the fetch/normalization boundary should remain easy to inspect and test. Fixture payloads may be retained in the repository test suite when sanitized and reasonably sized. A production raw-payload archive is not required by Phase 1 and must not be added implicitly without an explicit retention decision.

## Job lifecycle

The durable work unit remains one `(soldier_id, resource)` pair. Phase 1 handles `resource='detailed'` only.

The live queue lifecycle is:

```text
pending -> claimed -> running -> finalized
                         |
                         +-> retry/deferred state on retryable failure
                         +-> unavailable/terminal state when classification proves it
```

Successful jobs are removed from the actionable queue; durable outcome/history belongs in `collection_state` and `collection_events`.

A collector owns at most one Battlelog resource job at a time. Claims use PostgreSQL row locking (`FOR UPDATE SKIP LOCKED` or an equivalent atomic operation) so multiple collectors cannot own the same logical job.

A claim records the stable collector identity, `claimed_at`, `lease_expires_at`, and a unique `lease_token`. Any transition to running or finalization must verify current lease ownership using the token. Collector name alone is insufficient.

If the collector dies, the job remains unavailable until lease expiry and is then reclaimable. A stale/zombie collector must be unable to finalize work after another collector has reclaimed it.

Exact lease duration and heartbeat interval are runtime configuration values, not schema constants.

## Atomic success contract

A successful detailed collection is one database transaction containing all applicable authoritative effects:

1. upsert `detailed_stats_current`;
2. compare against the most recent detailed history snapshot and append `detailed_stats_history` only when the retained state meaningfully differs;
3. update the `detailed` row in `collection_state` with success/freshness metadata;
4. append the structured success event to `collection_events`;
5. remove/finalize the live `collection_jobs` row while verifying the current lease token.

Either all of those effects commit or none do. A crash before commit must leave last-known-good statistics intact and the job recoverable after lease expiry.

## History semantics

`detailed_stats_current` is refreshed on every successful normalized fetch.

`detailed_stats_history` is append-only and receives a new snapshot only when one or more retained detailed-stat fields differ from the most recent snapshot. Poll time alone is not a meaningful change and must not create duplicate history.

## Collector registration

The Phase 1 process uses a stable collector identity and the existing BF4PS collector registry semantics. Startup registers/refreshes the collector and current liveness is maintained without generating an event for every successful heartbeat.

The initial `tcou` collector identity must be explicit/configurable rather than inferred in a way that would collide when BF4PS later moves to distributed workers.

## Battlelog request gate

Phase 1 uses a conservative database-coordinated request gate before every Battlelog request. The gate represents the egress request budget, not process count.

The implementation may adapt the proven PostgreSQL serialization pattern used by BF4 Server Watcher, but BF4SW Keeper/persona timing constants are **not** BF4PS defaults. Detailed-statistics endpoint behavior must be measured independently.

The initial rate must be intentionally conservative and configurable. The collector must not increase request rate automatically based on apparent success during Phase 1.

## HTTP/failure classification

The collector must distinguish at least:

- HTTP throttle/rate-limit behavior, including observed relevant 403 responses;
- timeout/connection/network failure;
- HTTP 5xx/transient Battlelog failure;
- meaningful not-found/unavailable soldier/resource response;
- malformed JSON or source-schema/normalization failure;
- BF4PS/PostgreSQL/infrastructure failure.

Retryable failures preserve last-known-good statistics and schedule later eligibility/backoff. Terminal/unavailable classification must be based on observed Battlelog semantics, not guessed from a single generic transport failure.

Phase 1 starts with conservative configurable timeout/backoff values. Production retry timing is deliberately not frozen until live endpoint behavior is measured.

## Structured events

Collector actions use the existing append-only `collection_events` model. Events must provide enough structured information to identify collector, job, soldier/persona/platform, resource, event type, attempt, duration, HTTP status where applicable, and concise failure classification where applicable.

Raw Battlelog payload bodies are never event-log content.

## Initial validation cohort

Before any feeder exists, manually enqueue approximately 5-10 known soldiers. The cohort should cover all three supported platforms and include the known reconnaissance soldiers where useful:

- PC: `mauirixxx`, persona `236753552`;
- PS4: `xSilverMystx`, persona `303498475`;
- Xbox One: `S0UL OF STEEL`, persona `928420744`.

The cohort should also include at least one already-known BF4PS soldier that can be recollected so current/history idempotency can be inspected.

## Live queue/lease validation

The queue ownership primitives were validated live against the `bf4_playerstats_test` PostgreSQL database on `tcou` before wiring the Battlelog collector.

The validation harness `scripts/phase1_queue_race.py` registered two temporary collectors and made both contend concurrently for one `detailed` collection job. The observed result satisfied the Phase 1 ownership contract:

- exactly one collector won the simultaneous claim and the other received no job;
- the winning claim transitioned successfully from `claimed` to `running`;
- after the deliberately short lease expired, the other collector reclaimed the same job;
- reclamation rotated the `lease_token` and incremented `attempt_count`;
- the stale original owner was rejected when it attempted to finalize using its old fencing token;
- the current owner was allowed to transition to running and finalize the job;
- finalization removed the actionable queue row;
- both temporary collector-registry rows were removed after validation.

This live test demonstrates the PostgreSQL contention, lease-expiry recovery, and stale-owner fencing behavior required by the Phase 1 contract. It supplements the unit tests rather than replacing them.

## Phase 1 acceptance gate

Phase 1 is successful only after live test-database validation demonstrates all of the following:

- manual detailed jobs can be created without duplicate actionable work;
- the collector atomically claims exactly one job;
- Battlelog detailed JSON is fetched and normalized for PC, PS4, and Xbox One;
- retained current fields match the Detailed Stats Retention Contract v1;
- repeated unchanged collection updates current freshness without creating duplicate history;
- changed retained state creates exactly one new history snapshot;
- success updates collection state, writes a structured event, and removes/finalizes the actionable job atomically;
- retryable failure preserves last-known-good statistics and produces recoverable work/state;
- lease expiry permits recovery by a new collector while a stale lease token cannot finalize;
- the request gate prevents collectors sharing an egress identity from exceeding the configured start rate;
- no unexplained 403/throttle behavior appears during the tiny cohort test;
- unit/integration tests pass and live database inspection shows no stuck jobs or inconsistent state.

Only after this gate passes should BF4PS implement the bounded bootstrap feeder and begin measuring sustained detailed-statistics throughput. Distributed deployment comes after the single-node collector behavior is proven.

## Explicitly deferred

Phase 1 does not decide or implement:

- automatic population of the full BF4SW backlog;
- production polling cadence;
- final throughput/rate constants;
- profile collection;
- weapons or vehicles collection;
- dedicated interactive collection;
- the eight-node background deployment;
- production failover/drain orchestration beyond the lease/collector primitives required to prove safe recovery.

These remain later phases and must not be allowed to expand Patient Zero scope.