# Phase 2 single-node automatic runtime live validation

Date: 2026-10-04 UTC

Branch: `feature/phase2-single-node-loop`

Database: `bf4_playerstats_test`

Alembic revision: `0003_request_gates`

## Purpose

This record captures the first successful bounded automatic Phase 2 detailed-statistics collection cycle.

Unlike the earlier Patient Zero and manually bounded cohort validations, this test exercised the automatic runtime path: the bounded feeder materialized work, the runtime claimed and processed that work through the real Battlelog detailed-statistics path, persistence finalized successful jobs, and the collector stopped cleanly after its configured job ceiling.

## Preflight

Immediately before the live run, `scripts/phase2_single_node_preflight.py` was run in read-only mode.

Validated conditions:

- database: `bf4_playerstats_test`;
- PostgreSQL recovery state: false;
- Alembic revision: `0003_request_gates`;
- target depth: 3;
- maximum jobs: 3;
- population boundary: `soldier_id <= 6`;
- resource/lane: `detailed/background`;
- existing detailed/background queue: empty;
- database writes during preflight: 0;
- external requests during preflight: 0.

The exact expected bootstrap cohort was:

- soldier 3, PC, persona `1006267119911`, `kKaayyyy`;
- soldier 5, PC, persona `178801213`, `Strategery`;
- soldier 6, PC, persona `190251467`, `thepoet11`.

All three had no current detailed-stat row, no prior detailed success, and `detailed_state = 'never_attempted'`.

Preflight result:

`PHASE 2 SINGLE-NODE AUTOMATIC PREFLIGHT: PASS`

## Automatic runtime result

The live harness `scripts/phase2_single_node_live.py` rechecked its hard safety boundary before starting. The detailed/background queue was still empty and the selected cohort was still exactly soldier IDs 3, 5, and 6.

The bounded runtime then produced:

- feeder passes: 1;
- jobs materialized: 3;
- jobs attempted: 3;
- jobs succeeded: 3;
- jobs failed: 0;
- stopped by operator control: false.

Observed successful source timestamps:

- soldier 3 / `kKaayyyy`: `2026-10-04 05:45:33.096086+00:00`;
- soldier 5 / `Strategery`: `2026-10-04 05:45:34.890535+00:00`;
- soldier 6 / `thepoet11`: `2026-10-04 05:45:36.931336+00:00`.

Each soldier finished with `detailed_state = 'success'`, and `detailed_last_success_at` matched the persisted `detailed_stats_current.source_fetched_at` shown by the validation harness.

## Final validation

The live harness reported:

- exact bounded attempts: PASS;
- collector clean stop: PASS;
- operator controls preserved: PASS;
- all cohort soldiers attempted: PASS;
- all collections successful: PASS;
- cohort queue finalized: PASS.

Final result:

`BF4PS PHASE 2 SINGLE-NODE LIVE RUN: PASS`

## Preservation

No cleanup was performed. The successful detailed-statistics/current/history/state/event evidence from this first automatic bootstrap cohort is intentionally retained in the test database.

The one-shot validation harness should not be rerun against this same cohort. Its exact-cohort safety checks are intended to prevent accidental reuse once these soldiers are no longer `never_attempted`.

## Milestone

This is the first live validation that BF4PS can autonomously move a bounded cohort through the complete Phase 2 path:

`bounded feeder -> collection queue -> claim/lease -> PostgreSQL request gate -> Battlelog detailed fetch -> normalization -> atomic persistence -> queue finalization -> clean collector stop`

The next expansion should remain bounded rather than opening the full durable backlog. A larger small cohort can be used to validate sustained request gating, repeated feeder/replenishment behavior, heartbeat/control behavior, and handling of heterogeneous Battlelog outcomes before increasing the workload further.
