# Phase 5A — Weapon/Vehicle Implementation Census

Status: **STOP GATE REACHED — production weapon/vehicle collection does not yet exist**

This census follows the frozen Phase 5A full-stats cost-characterization design. It answers the required question before any expensive Battlelog traffic is generated: which weapon/vehicle production components already exist, and which must be implemented before a Phase 5A live harness is allowed to run?

## Schema prerequisite

The repository schema reference and current Alembic chain were reviewed before this census. The current migration chain is:

- `0001_initial_schema`
- `0002_drop_gun_master_score`
- `0003_request_gates`

The existing schema already defines the Phase 5A persistence targets and resource state families. No Phase 5A schema migration is currently justified by this census.

## Existing production collection implementation

The `bf4ps/` package currently contains production machinery for detailed-statistics collection:

- `battlelog_detailed.py`
- `detailed_collector.py`
- `detailed_failure.py`
- `detailed_persistence.py`
- shared queue/runtime/request-gate components

The package does **not** contain weapon- or vehicle-specific Battlelog clients, normalizers, collectors, persistence modules, or failure modules.

The unit-test tree likewise contains detailed-statistics tests but no weapon- or vehicle-specific normalization/persistence/collector tests.

Therefore the database schema is ahead of the production collector implementation: weapon and vehicle storage/state contracts exist, but there is not yet production code that can populate them through the normal lifecycle.

## Battlelog source contract already established

Reconnaissance has already established structured anonymous endpoints for all three supported BF4 platforms:

- `/bf4/warsawWeaponsPopulateStats/{persona_id}/{platformInt}/stats/`
- `/bf4/warsawvehiclesPopulateStats/{persona_id}/{platformInt}/stats/`

The documented retention contract also already constrains what may be normalized and persisted.

Weapons retain stable catalog identity plus player-specific kills, headshots, shots fired, shots hit, and time equipped. Battlelog accuracy, score, deaths, service stars, progression/unlocks, images, suggestions, and UI metadata remain excluded.

Vehicles retain stable catalog identity plus player-specific kills and time in vehicle, with `destroy_x_in_y` only according to the established schema contract. Service stars, progression/unlocks, images, suggestions, and UI metadata remain excluded.

## Missing implementation required before live Phase 5A

Phase 5A cannot legitimately jump straight to census/preflight/live execution. The following production pieces must first be built and tested against the documented schema and Battlelog contracts:

1. weapon Battlelog request + explicit payload normalization;
2. vehicle Battlelog request + explicit payload normalization;
3. weapon catalog/current-state persistence;
4. vehicle catalog/current-state persistence;
5. resource-specific success/failure lifecycle handling for `weapons` and `vehicles`;
6. integration with the existing collection-job ownership/lease machinery and PostgreSQL request gate;
7. unit tests proving normalization rejects malformed required structures rather than guessing;
8. persistence tests proving only retained fields reach the documented tables and current-state replacement is transactionally safe;
9. lifecycle tests proving temporary failures leave retryable pending/unowned jobs and successful attempts converge state cleanly;
10. response-byte instrumentation if Phase 5A is to report measured bandwidth rather than only reconnaissance planning estimates.

## Reuse boundary

Existing detailed-statistics code is a pattern and shared infrastructure source, not a schema template. Weapon and vehicle payloads have their own source shapes and retention rules. Implementations must not force those payloads through `battlelog_detailed.py` or `detailed_persistence.py` merely to reduce file count.

Shared queue, collector registry, lease, request-gate, and generic failure semantics should be reused where their existing contracts are resource-agnostic.

## Stop decision

The frozen Phase 5A design explicitly requires a stop if a required weapon/vehicle collector or normalizer does not exist. That condition is confirmed.

Accordingly:

- **do not select/freeze the 30-player live cohort yet;**
- **do not issue weapon or vehicle Battlelog requests yet;**
- **do not write a live Phase 5A worker that embeds ad-hoc normalization/persistence;**
- **do not change the database schema merely to simplify implementation.**

The next work item is production implementation of the weapon resource, followed by its unit/integration validation. Vehicle implementation follows using the same resource architecture. Once both resources are independently validated, Phase 5A returns to its frozen sequence: read-only cohort census → freeze 10/10/10 → preflight → weapon stage → audit → vehicle stage → audit → final cost characterization.

## Implementation order

To minimize simultaneous unknowns, implementation should proceed in this order:

1. weapon source client/normalizer;
2. weapon persistence;
3. weapon lifecycle collector integration + tests;
4. vehicle source client/normalizer;
5. vehicle persistence;
6. vehicle lifecycle collector integration + tests;
7. measured response-size instrumentation shared by both expensive resources;
8. Phase 5A census and live harness.

No live Battlelog request is required to complete the first implementation pass: use captured/fixture payload shapes and unit tests first. Live requests resume only when a narrowly bounded validation is ready.