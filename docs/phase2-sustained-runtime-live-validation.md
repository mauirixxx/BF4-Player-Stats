# Phase 2 Sustained Runtime Live Validation

## Result

**PASS**

The bounded single-node Phase 2 runtime successfully completed a sustained ten-job live validation against `bf4_playerstats_test` on 2026-10-04 UTC.

This validation intentionally retained the collected statistics, history, collection state, and collection events as test evidence.

## Safety boundary

The live harness required all of the following before starting the runtime:

- database name containing `test`;
- PostgreSQL primary (`pg_is_in_recovery() = false`);
- Alembic revision `0003_request_gates`;
- empty `detailed/background` queue;
- exact expected cohort of soldier IDs 7 through 16;
- `max_soldier_id = 16`;
- `target_depth = 1`;
- hard `max_jobs = 10` attempt ceiling.

The validated cohort was:

| soldier_id | platform | player |
| ---: | --- | --- |
| 7 | pc | thermalnuclearwa |
| 8 | pc | SultanOfkabobs |
| 9 | pc | xaikgr |
| 10 | pc | demetrej |
| 11 | pc | kukurusich |
| 12 | pc | max73max |
| 13 | pc | ImNotaChad |
| 14 | pc | daChilli-Man |
| 15 | pc | jdisa35w |
| 16 | pc | WT_Stall |

## Runtime result

The sustained run produced:

- jobs attempted: **10**;
- jobs succeeded: **10**;
- jobs failed: **0**;
- feeder passes: **10**;
- jobs materialized: **10**;
- stopped by operator control: **false**.

Because the working queue target depth was exactly one, ten feeder passes and ten materialized jobs demonstrate repeated bounded replenishment rather than processing one preloaded batch.

Each cohort soldier finished with `detailed_state = success` and a populated `detailed_stats_current.source_fetched_at` value.

## Final validation

The live harness reported PASS for all of the following:

- exact ten-attempt ceiling;
- repeated feeder replenishment;
- exactly ten jobs materialized;
- no work materialized beyond soldier ID 16;
- clean collector stop;
- operator controls preserved;
- all ten cohort soldiers attempted;
- all ten collections successful;
- cohort queue finalized.

No cleanup was performed after the run. The resulting evidence remains in the test database.

## Significance

This is the first BF4PS Phase 2 validation to demonstrate the automatic collector runtime sustaining work across repeated feeder cycles rather than consuming only an initially materialized cohort.

With `target_depth = 1`, every completed job forced the runtime to return through the feeder path before another new bootstrap job could become available. The successful 10/10 run therefore validates the bounded feeder, queue claim/collection/finalization path, request-gated Battlelog collection, collection-state persistence, and runtime lifecycle together across repeated iterations.
