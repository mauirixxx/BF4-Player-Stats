# BF4PS Phase 3E final clean-stop closure

Status: **PASS**

Date: 2026-10-05 UTC

Parent validation record: `docs/phase3e-lifecycle-validation-plan.md`

Current Alembic head: `0003_request_gates`

## Purpose

This record preserves the final Phase 3E convergence and clean-stop evidence after the abrupt-loss survivor-progress experiment. It closes the remaining acceptance requirement that all three frozen collectors stop cleanly after the experiment without erasing or manufacturing the earlier abrupt-loss evidence.

## Frozen identities

| Host | Collector | Stable UUID |
|---|---|---|
| `hnl-01` | `phase3e-hnl-01` | `b2b3ef60-62e8-4d4a-91b0-41a2e2a3e001` |
| `kah-01` | `phase3e-kah-01` | `b2b3ef60-62e8-4d4a-91b0-41a2e2a3e002` |
| `tcou` | `phase3e-tcou` | `b2b3ef60-62e8-4d4a-91b0-41a2e2a3e003` |

All closure work remained restricted to `bf4_playerstats_test` on `mak-db-02.bf4statusbot.com` at Alembic head `0003_request_gates`.

## Abandoned victim recovery — PASS

The survivor-progress experiment intentionally left job **814**, soldier **390** (`ObiJuanQueHuevos`), as an abandoned attempt-1 ownership checkpoint after `hnl-01` was terminated without lease renewal or clean release.

After unrelated survivor jobs 815 and 816 completed successfully on `kah-01`, job 814 was resolved through the normal production ownership/collection path rather than by administrative deletion, reset, reseeding, or fabricated event history.

The closure harness observed the expected expired attempt-1 ownership tuple:

- owner: `phase3e-hnl-01` / UUID `b2b3ef60-62e8-4d4a-91b0-41a2e2a3e001`;
- lease token: `3d0cf2d7-22d1-4b4e-b9a4-b034cc048009`;
- attempt: **1**;
- lease: expired naturally.

`kah-01` then reclaimed the same logical job through the production detailed collector path. Reclamation incremented the attempt to **2** and rotated the lease token. The authorized Battlelog request returned HTTP **200**, `history_appended=True`, detailed current/state persistence converged, and the queue row finalized.

The durable terminal result is:

| Event | Job | Soldier | Attempt | Collector | HTTP | Result |
|---:|---:|---:|---:|---|---:|---|
| 814 | 814 | 390 | 2 | `phase3e-kah-01` | 200 | `collection_success` |

The harness reported:

- cross-host reclamation: **PASS**;
- attempt increment 1 -> 2: **PASS**;
- lease-token rotation: **PASS**;
- queue finalization: **PASS**;
- detailed state/current persistence: **PASS**;
- reclaimer cleanly released current job: **PASS**.

This preserves the original abrupt-loss evidence while proving eventual normal recovery of the abandoned victim.

## Final clean-stop preflight — PASS

A read-only preflight then verified:

- all three stable collector identities remained exact;
- all three were enabled and undrained;
- none owned a current job;
- events 812, 813, and 814 exactly represented survivor jobs 815/816 and recovered victim job 814;
- closure jobs 814, 815, and 816 were absent from `collection_jobs`.

Observed preflight registry state:

| Host | Heartbeat | Current job | Enabled | Drained |
|---|---|---|---|---|
| `hnl-01` | `healthy` | none | true | false |
| `kah-01` | `healthy` | none | true | false |
| `tcou` | `unknown` | none | true | false |

The preflight performed zero database writes and zero Battlelog requests.

## Production clean-stop execution — PASS

The final closure invoked the production `stop_collector()` primitive for each of the three frozen collector UUIDs. No direct SQL cleanup path was substituted for the production lifecycle primitive.

Before stop:

- `hnl-01`: `heartbeat=healthy`, `current_job=None`, `enabled=True`, `drained=False`;
- `kah-01`: `heartbeat=healthy`, `current_job=None`, `enabled=True`, `drained=False`;
- `tcou`: `heartbeat=unknown`, `current_job=None`, `enabled=True`, `drained=False`.

All three `stop_collector()` calls returned **PASS**.

After stop:

- `hnl-01`: `heartbeat=unknown`, `current_job=None`, `enabled=True`, `drained=False`;
- `kah-01`: `heartbeat=unknown`, `current_job=None`, `enabled=True`, `drained=False`;
- `tcou`: `heartbeat=unknown`, `current_job=None`, `enabled=True`, `drained=False`.

Final invariants reported by the closure harness:

- all three production clean-stop markers persisted: **PASS**;
- all `current_job_id` values clear: **PASS**;
- operator-owned `enabled`/`drained` controls preserved: **PASS**;
- closure events 812..814 preserved: **PASS**;
- closure jobs 814..816 remain absent: **PASS**;
- active jobs owned by frozen collectors: **0**;
- collection jobs created: **0**;
- Battlelog requests: **0**;
- harness exit code: **0**.

## Conclusion

**Phase 3E final clean-stop closure is PASS.**

The remaining acceptance gap is closed: the abandoned victim recovered naturally through cross-host lease reclamation and the production detailed collector path, all closure jobs converged out of the queue, historical events remained intact, no frozen collector retained ownership, operator controls were preserved, and all three frozen collectors were intentionally marked stopped through the production lifecycle primitive.

The next action is a read-only final acceptance audit. If that reconciliation matches the preserved evidence, Phase 3E can be declared complete and work can proceed to the next distributed collection stage.