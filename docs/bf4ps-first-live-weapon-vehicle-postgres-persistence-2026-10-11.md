# BF4PS — first live weapons and vehicles PostgreSQL checkpoint (2026-10-11)

**PASS — real Battlelog weapon and vehicle statistics persisted into the isolated Stage 9C integration scratch DB. Production HOLD unchanged.**

## Preflight and execution

- Host: `tcou`.
- Database: `bf4ps_scratch_stage9c_integration`, role `bf4ps_stage9c_integration`, writable primary, revision `0004_stage9c_supervision_runs`.
- Soldier: PC persona `236753552`, `soldier_id=49`; the previously retained successful detailed-stat fixture.
- Existing collector: `live-persistence-validation-tcou`; one bounded attempt per resource, existing background admission, 10-second egress request gate, 120-second lease, 30-second HTTP timeout, 3600-second retry deferral. No fleet activation.
- GitHub script: `scripts/stage9c_live_resource_persistence.py` at commit `586e10b`.
- Script fetched from GitHub to `/tmp/bf4ps-stage9c-resource.py` on tcou, syntax-compiled, executed separately for weapons and vehicles.

## Live results

| Check | Weapons | Vehicles |
| --- | ---: | ---: |
| Collection status | PASS | PASS |
| Soldier stat rows | 174 | 82 |
| Catalog rows | 174 | 82 |
| Response bytes | 553387 | 454759 |
| Fetch/normalize duration (ms) | 1221 | 805 |
| Attempt-start events | 1 | 1 |
| Success events | 1 | 1 |
| Remaining resource jobs | 0 | 0 |

Vehicle process independently confirmed exit code 0. Both collector invocations printed `LIVE ... PERSISTENCE PASS`.

## Independent database verification

- `collection_state`: `detailed_state=success`, `weapons_state=success`, `vehicles_state=success`.
- `detailed_stats_current=1`, `detailed_stats_history=1`.
- `soldier_weapon_stats=174`, `weapon_catalog=174`.
- `soldier_vehicle_stats=82`, `vehicle_catalog=82`.
- `collection_jobs=0`.
- Detailed: two attempt-start and two success events (original + successful repeat).
- Weapons: one attempt-start and one success event.
- Vehicles: one attempt-start and one success event.

**The database rows remain in place** for subsequent tests. This validation harness deliberately rejects reruns for an already-attempted resource; use a new cohort or explicit repeat design for later collections.

## Scope

Confirms live fetch, normalization, catalog reconciliation, current-stat persistence, resource state and durable attempt/success events for one PC soldier. Does **not** prove multi-soldier or multi-platform live coverage, global physical HTTP cap under arbitrary failures, or production distributed collector readiness. Next: a bounded multi-soldier cohort and cross-platform coverage, with schema-verified idempotent setup and per-resource reconciliation.
