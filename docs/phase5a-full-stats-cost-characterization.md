# Phase 5A — Full-Stats Multiplatform Cost Characterization

Status: **IN PROGRESS — Stage A weapons accepted; Stage B vehicles preparing**

## Purpose

Phase 4C proved distributed `detailed` collection across PC, PS4, and Xbox One. Phase 5A is the first deliberately expensive test: characterize the real request, payload, persistence, and lifecycle cost of collecting a soldier's retained BF4 statistics when the weapon and vehicle resources are included.

This is a characterization phase, not a bulk-ingestion phase. Its job is to establish a trustworthy cost model and validate weapon/vehicle normalization and persistence before BF4PS attempts sustained full-database collection.

## Existing contracts this phase must preserve

The current documented Alembic head is `0003_request_gates`. No schema change is planned for Phase 5A.

BF4PS has four independent collection resources: `detailed`, `profile`, `weapons`, and `vehicles`. `collection_state` remains one row per soldier with resource-prefixed state families. Queue resource identity belongs in `collection_jobs.resource`.

Weapon persistence is current-state only through `weapon_catalog` and `soldier_weapon_stats`. Vehicle persistence is current-state only through `vehicle_catalog` and `soldier_vehicle_stats`. Phase 5A must not invent weapon or vehicle history tables.

The Battlelog reconnaissance contract established anonymous structured endpoints for detailed, weapon, and vehicle statistics on PC, PS4, and Xbox One. Representative payloads were approximately 5.5–5.7 KB detailed, 582–588 KB weapons, and 453–454 KB vehicles. This is the reason Phase 5A is intentionally bounded.

## Retained weapon data

For each observed weapon, BF4PS retains the stable weapon GUID plus catalog name/slug/category and these per-soldier counters:

- kills;
- headshots;
- shots fired;
- shots hit;
- time equipped in seconds.

Battlelog accuracy, score, deaths, service stars, unlock/progression data, suggestions, images, and presentation metadata remain excluded.

## Retained vehicle data

For each observed vehicle, BF4PS retains the stable vehicle GUID plus catalog name/slug/category and these per-soldier values:

- kills;
- time in seconds;
- `destroy_x_in_y` when supplied/retained by the established schema contract.

Service stars, unlock/progression data, suggestions, images, and presentation metadata remain excluded. Vehicle history is not introduced.

## Test cohort

Phase 5A begins with **30 frozen soldiers**:

- 10 PC;
- 10 PS4;
- 10 Xbox One.

Cohort selection must be deterministic and read-only. Candidates must already have successful detailed collection so this phase isolates weapon/vehicle cost rather than re-testing the Phase 4 detailed collector. Candidates must begin with pristine `weapons_state = 'never_attempted'` and `vehicles_state = 'never_attempted'`, no weapon/vehicle jobs, and no existing per-soldier weapon/vehicle rows.

The census must capture `(soldier_id, persona_id, current_name, platform)` and write only the generated Python cohort file; it must perform zero database writes and zero Battlelog requests.

## Execution stages

Phase 5A deliberately separates the expensive resources so failures and cost can be attributed correctly.

### Stage A — weapons

Run one weapon collection attempt per frozen soldier through the normal collection lifecycle and PostgreSQL request gate. Do not issue vehicle requests during this stage.

After the stage, perform a read-only audit before continuing. Record per-platform success/failure shape, request duration, response/persistence evidence, catalog growth, per-soldier row counts, lifecycle state, residual retry jobs, and 403/429/throttle evidence.

### Stage B — vehicles

Only after the weapon stage is reconciled, run one vehicle collection attempt per frozen soldier through the same lifecycle and request-gate machinery.

Perform the same read-only reconciliation for vehicle state, catalog growth, per-soldier rows, retries, and throttle behavior.

### Stage C — cost characterization

Produce a final read-only report combining both stages. The report must quantify at minimum:

- attempted and successful soldiers by platform/resource;
- terminal and temporary-failure event counts;
- Battlelog request count represented by collection attempts;
- request duration distribution where event data permits it;
- weapon catalog row growth;
- vehicle catalog row growth;
- total and per-soldier `soldier_weapon_stats` rows;
- total and per-soldier `soldier_vehicle_stats` rows;
- residual retry jobs;
- 403/429/throttle evidence;
- elapsed wall-clock time supplied by the harness/run evidence;
- observed requests per completed full-stat soldier;
- observed bytes per soldier only if the collector records actual response size; otherwise report that actual byte cost is not yet instrumented rather than substituting reconnaissance estimates.

The report may use the reconnaissance payload sizes as clearly labeled planning context, but they are not measured Phase 5A traffic.

## Live weapon characterization checkpoint — 2026-10-06

Before the frozen 10/10/10 multiplatform cohort, Phase 5A used a deliberately smaller PC-only weapon checkpoint to validate real collector cost and lifecycle behavior.

The initial single-soldier probe succeeded with one Battlelog request, HTTP 200, 568,544 measured response bytes, 174 persisted weapon rows, and 1,405 ms request duration.

A subsequent 10-soldier PC cohort completed successfully after an intentionally preserved interrupted run. The first cohort invocation completed soldier 5 and then stopped before request two because the harness incorrectly supplied `max_total_attempts=1`. The queue's durable cohort-wide attempt ceiling therefore prevented a second claim exactly as designed. Jobs 2212-2220 remained pending, unowned, and at attempt count zero; their soldiers remained `weapons_state='never_attempted'`; and no weapon rows or attempt events were created for them. A bounded resume harness then completed exactly those nine preserved jobs.

Final 10-soldier evidence:

- successful requests: 10/10, all HTTP 200;
- total measured response bytes: 5,751,737 bytes (~5.49 MiB);
- mean response size: 575,174 bytes;
- median response size: 579,241 bytes;
- response-size range: 521,047-593,678 bytes;
- mean request duration: 1,480 ms;
- median request duration: 1,358 ms;
- duration range: 1,278-2,179 ms;
- persisted weapon rows: 173-174 per soldier, mean 173.3;
- temporary/HTTP failures: 0;
- no progressive latency increase was evident across the sequence at the 5-second PostgreSQL request-gate interval.

The reusable cohort harness must pass the requested cohort size as the durable `max_total_attempts` ceiling. A ceiling of one is valid only for a true single-attempt probe; it is not a per-call limit when the claim implementation counts durable completed cohort events.

This checkpoint validates PC weapon collection and provides measured cost evidence, but it does not replace the frozen 30-soldier 10/10/10 multiplatform Phase 5A acceptance cohort defined below.

## Request pacing

Phase 5A must use the existing PostgreSQL-coordinated `request_gates` mechanism and the three established collector egress identities. It must not add a special fast path or bypass the gate because the purpose is to measure realistic production behavior.

Only the three established collectors are in scope:

- `phase3e-hnl-01` on `hnl-01`;
- `phase3e-kah-01` on `kah-01`;
- `phase3e-tcou` on `tcou`.

The exact collector UUIDs must be obtained from the established frozen collector contract/current registry code rather than guessed.

## Failure semantics

Malformed or missing Battlelog structures are lifecycle outcomes, not process crashes. Normalization failures must use the same retryable failure semantics established by the collection architecture unless existing resource-specific contracts explicitly classify a response as unavailable.

A temporary failure is acceptable Phase 5A evidence when:

- an attempt event exists;
- collection state reflects the latest attempt;
- the retry job is lifecycle-valid, pending/unowned when not executing;
- partial or invalid resource data is not presented as a successful collection;
- other collectors continue operating.

HTTP 403/429 or throttle events do not automatically invalidate the experiment, but they must be surfaced prominently and reconciled before scaling further.

## Safety boundaries

Phase 5A must stop rather than silently broaden scope if any of these occur:

- schema documentation and current Alembic migrations disagree;
- a required weapon/vehicle collector or normalizer does not yet exist;
- the Battlelog payload shape cannot be mapped to the frozen retention contract without guessing;
- persistence would require a schema change not covered by this design;
- queue ownership/lease semantics would need to be bypassed;
- a collector crashes rather than recording a lifecycle outcome;
- foreign resource jobs appear and would contaminate cost accounting.

## Preflight requirements

Before ignition, a turn-key preflight must prove:

- exact frozen 10/10/10 identities unchanged;
- all 30 have successful detailed state;
- all 30 weapon and vehicle states are pristine;
- no frozen weapon/vehicle jobs exist;
- no foreign weapon/vehicle/background jobs contaminate the run;
- no frozen soldier already has weapon/vehicle persistence rows;
- the three stable collectors are enabled, undrained, idle, and identity-correct;
- the three required request gates exist;
- no prior Phase 5A weapon/vehicle attempt events exist for the frozen cohort;
- database writes: 0;
- Battlelog requests: 0.

## Acceptance boundary

Phase 5A passes when the experiment is fully reconciled, not merely when every Battlelog response succeeds.

A successful acceptance must prove that every issued weapon/vehicle attempt is represented by lifecycle-valid events and state, successful resources persist only retained data into the documented tables, catalog identities converge without duplicate GUIDs, residual jobs exactly match unresolved retryable outcomes, no foreign jobs contaminate the experiment, collector ownership is clean at rest, and no worker crashes occur.

The final report must explicitly distinguish:

1. **resource correctness** — normalization/persistence/lifecycle behavior is correct;
2. **transport behavior** — throttling and request failures observed;
3. **cost** — requests, durations, row amplification, and measured bytes if instrumented.

## What Phase 5A does not do

- It does not collect Battlelog profile enrichment.
- It does not create weapon or vehicle history.
- It does not ingest the full BF4PS soldier population.
- It does not change production refresh cadence.
- It does not infer unmeasured bandwidth from payload-size reconnaissance.
- It does not scale beyond the frozen 30-player cohort until both resource stages and the final characterization audit pass.

## Next decision

After Phase 5A acceptance, use the measured request/duration/persistence amplification to choose the first sustained full-stat cohort size and safe per-resource refresh strategy. Only then should BF4PS estimate the wall-clock and bandwidth cost of completing weapon + vehicle bootstrap for the full discovered soldier database.


## Stage A distributed run #1 — failed-run evidence (2026-10-06)

The first three-collector Stage A execution is retained as a failed characterization
run and diagnostic checkpoint. It MUST NOT be counted as Stage A acceptance even
though the original post-run audit reported PASS.

Observed behavior:

- the frozen 30-job cohort was seeded cleanly with zero prior weapon/vehicle
  persistence or events;
- all visible Battlelog responses were HTTP 200 and no 403/429/throttle signal
  was observed;
- `tcou` crashed during successful-response persistence with a PostgreSQL
  deadlock in `weapon_catalog`;
- `kah-01` later crashed with the same deadlock signature;
- `hnl-01` continued and the database ultimately contained 30 terminal
  successful weapon events, one per frozen soldier;
- the original audit therefore reported 30/30 durable successes and zero
  failures, despite the two worker crashes.

Root cause: successful weapon persistence reconciled roughly 173-174 shared
global `weapon_catalog` identities inside each collector transaction using
`INSERT ... ON CONFLICT DO UPDATE`. Concurrent collectors could acquire
overlapping catalog/unique-index locks in conflicting orders, producing a
deadlock cycle.

The run also exposed an accounting defect. The HTTP request happened before the
successful persistence transaction. When PostgreSQL aborted a deadlocked
persistence transaction, the terminal event rolled back with it even though the
network request had physically occurred. The durable terminal-event count could
therefore undercount real Battlelog requests. The run produced at least two such
unrecorded physical requests and is not valid cost-characterization evidence.

Required correction before Stage A rerun:

1. serialize the shared weapon-catalog persistence critical section across
   collectors with a PostgreSQL transaction-scoped advisory lock and reconcile
   weapon GUIDs in deterministic order;
2. commit a `collection_attempt_started` event immediately before each physical
   HTTP request so later persistence rollback cannot erase request evidence;
3. make the bounded-attempt ceiling count unique durable started/terminal
   attempts plus not-yet-started active reservations;
4. require the Stage A audit to reconcile exactly 30 durable physical attempts
   with exactly 30 terminal outcomes and require participation by all three
   frozen collectors;
5. after any post-request persistence exception rolls back, append a
   `collection_persistence_failure` event in a fresh transaction and make any
   such event fatal to Stage A acceptance. The diagnostic event must preserve
   the original exception class/message plus job, attempt, collector, lease,
   response-byte, and persistence-stage context without replacing the original
   exception if diagnostic logging itself fails.

The failed run remains useful evidence: resource normalization succeeded for all
30 soldiers eventually and transport showed no observed throttling, while the
distributed persistence/accounting layers failed acceptance.


## Stage A Run #2 reset and evidence boundary

Run #1 remains preserved in `collection_events` as failed-run forensic evidence. Preparing Run #2 must not delete or rewrite that ledger history merely to make the experiment harness pristine.

The guarded Run #2 reset therefore:

- requires the exact frozen test database/revision and the expected completed Run #1 shape;
- requires no contaminating background/weapon/vehicle jobs and idle frozen collectors;
- removes only the frozen cohort's current `soldier_weapon_stats` rows;
- resets only the weapon-prefixed `collection_state` fields to the documented pristine state;
- leaves soldier identity, detailed statistics, vehicle state/data, the global weapon catalog, and all historical collection events intact;
- appends a durable `phase5a_stage_a_run_started` boundary event for Run #2.

Run #2 bounded-attempt accounting, worker safety checks, ignition, and post-run audit scope collection-event evidence to event IDs after that durable boundary. Historical Run #1 events therefore remain queryable without consuming Run #2's 30-attempt ceiling or contaminating its acceptance audit.


## Stage A Run #2 — accepted distributed weapon characterization (2026-10-06)

Run #2 preserved all failed Run #1 forensic events and used durable boundary event
`2299` to scope the rerun. The guarded reset removed only the frozen cohort's
current `soldier_weapon_stats` rows, reset only the weapon-prefixed collection
state, preserved the global weapon catalog and all historical events, and issued
zero Battlelog requests.

The post-reset ignition passed with zero writes and zero Battlelog requests. The
frozen 10 PC + 10 PS4 + 10 Xbox One identities were unchanged, all 30 detailed
states remained successful, weapon and vehicle states were pristine, no
per-soldier weapon/vehicle rows or jobs existed, all three frozen collectors were
identity-correct and idle, all three request gates existed, and no current-run or
foreign background work contaminated the experiment.

Run #2 seeded jobs 2251-2280 and executed them concurrently on the three frozen
collectors. Worker participation was:

- `phase3e-hnl-01`: 8 physical attempts;
- `phase3e-kah-01`: 8 physical attempts;
- `phase3e-tcou`: 14 physical attempts.

The final read-only audit passed every acceptance check after boundary event 2299:

- durable physical attempts: 30 exactly;
- terminal outcomes: 30 exactly;
- start-to-terminal reconciliation: 30/30, one attempt per frozen soldier;
- platform split: 10 PC / 10 PS4 / 10 Xbox One;
- successes: 30; failures: 0;
- HTTP 403/429/throttle evidence: 0;
- `collection_persistence_failure` evidence: 0;
- residual retry jobs: 0;
- persisted per-soldier weapon rows: 5,201 total (173-174 per soldier);
- measured response bytes: 17,575,509 total;
- response bytes mean 585,850.3, median 590,158, range 518,987-640,772;
- request duration mean 1,270.4 ms, median 1,211 ms, range 981-2,271 ms;
- worker crashes/deadlocks: 0.

Stage A Run #2 therefore passes resource correctness, distributed persistence,
transport behavior, physical-request accounting, lifecycle reconciliation, and
observability. The transaction-scoped advisory lock plus deterministic weapon
GUID ordering survived the three-collector workload that deadlocked Run #1.

Run #1 remains intentionally preserved as failed-run evidence. Its 30 terminal
successes understated physical network cost because two post-request persistence
deadlocks rolled back their terminal evidence; the run therefore made at least
32 physical Battlelog requests. The contrast between the preserved failed run
and accepted Run #2 is part of the Phase 5A evidence, not disposable test noise.

### Stage B readiness boundary

Stage B must leave the accepted Stage A weapon state and all Stage A event
history untouched. Vehicle work uses the same frozen 30 soldiers, collectors,
PostgreSQL request gates, queue/lease lifecycle, and hard 30-physical-attempt
ceiling, but all Stage B accounting is scoped to a new durable Stage B run
boundary.

Before a distributed vehicle run, implementation must validate the actual
Battlelog vehicle payload shape rather than infer it from weapon payloads or
schema column names. The source contract confirms the anonymous
`warsawvehiclesPopulateStats/{persona_id}/{platformInt}/stats/` endpoint, 82
vehicle entries in representative PC/PS4/Xbox One payloads, stable vehicle GUID,
kills, `timeIn`, `destroyXinY`, and catalog name/slug/category. Exact container
keys and null/type behavior remain implementation evidence to verify.

The first distributed vehicle collector must inherit the corrected Stage A
observability/concurrency contract from the outset:

1. commit `collection_attempt_started` immediately before the physical vehicle request;
2. serialize the shared `vehicle_catalog` persistence critical section with a
   transaction-scoped PostgreSQL advisory lock and deterministic vehicle-GUID order;
3. persist catalog reconciliation, replacement `soldier_vehicle_stats`,
   `vehicles_*` collection state, terminal event, and queue finalization atomically;
4. after any post-request persistence rollback, append
   `collection_persistence_failure` in a fresh transaction with vehicle-specific
   stage/response-byte context, then re-raise the original exception;
5. make the bounded attempt ceiling count durable physical starts within the
   Stage B boundary and require exact 30-start/30-terminal reconciliation;
6. stop on collector crash, foreign work, throttle evidence, schema mismatch,
   or any payload shape that would require guessing.

No Stage B schema migration is planned. Current head `0003_request_gates`
already provides `vehicle_catalog`, `soldier_vehicle_stats`, the `vehicles_*`
collection-state family, generic vehicle-capable queue/event rows, and request
gates.


## Stage B live normalization checkpoint — 2026-10-06

A bounded tcou probe made exactly one anonymous vehicle-statistics request for
frozen PC soldier 15 (`jdisa35w`, persona 513446234) and performed zero database
writes. Battlelog returned HTTP 200 and 452,007 measured response bytes.

The strict normalizer accepted exactly 82 `data.mainVehicleStats` rows with 82
unique vehicle GUIDs. The live payload had zero null slug rows, zero null category
rows, zero null `destroyXinY` rows, and zero non-integral `destroyXinY` rows.
Observed kills ranged 0-85, `timeIn` ranged 0-8,303 seconds, and the payload
contained 27 distinct categories.

This evidence validates the current schema's nullable BIGINT `destroy_x_in_y`
representation for the observed payload without rounding or coercion. Vehicle
persistence must nevertheless reject any future fractional `destroyXinY` value
rather than silently truncate it; such a payload would require explicit schema/
retention-contract reconciliation.


## Stage B single-soldier persistence/lifecycle checkpoint — 2026-10-06

A guarded first-write probe on tcou exercised frozen PC soldier 15 (jdisa35w, persona 513446234) through the normal vehicle queue, lease, PostgreSQL request gate, durable physical-attempt marker, strict normalizer, atomic persistence, terminal event, and queue finalization path.

The probe created durable boundary event 2360 and job 2281. Exactly one physical Battlelog request completed successfully: HTTP 200, 452,019 measured response bytes, 1,260 ms duration, and 82 normalized/persisted vehicle rows. The read-only audit proved exactly one durable collection_attempt_started and exactly one reconciled terminal success, no collection_persistence_failure, vehicles_state success, 82 current soldier_vehicle_stats rows, and no residual vehicle job.

The accepted Stage A weapon result was unchanged by the vehicle transaction: weapons_state success remained intact and all 173 weapon rows for soldier 15 remained present. This validates the vehicle persistence/lifecycle path in isolation before distributed Stage B.

The probe is forensic evidence and remains in collection_events. Before the distributed Stage B run, only soldier 15 current vehicle rows and vehicle-prefixed collection-state fields are reset to pristine. Probe event history, the global vehicle catalog, all weapon state/data/history, detailed data, and identities remain untouched. A new durable Stage B run boundary scopes the 30-attempt distributed characterization so the probe request does not consume the Stage B attempt ceiling.
