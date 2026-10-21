# Phase 5A — Full-Stats Multiplatform Cost Characterization

Status: **DESIGN FROZEN — implementation not yet started**

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
