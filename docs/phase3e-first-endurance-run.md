# BF4PS Phase 3E first endurance run

Status: **investigative run — not final Phase 3E acceptance**

Date: 2026-10-04 UTC

Design: `docs/phase3e-distributed-endurance-design.md`

Alembic head: `0003_request_gates`

## Purpose

This run was the first sustained three-host Phase 3E exercise using the frozen 120-soldier cohort, normal bounded feeder replenishment, a queue target of 6, a hard global attempt ceiling of 120, and 5-second BF4PS request-gate pacing.

It is preserved as investigative evidence rather than the final Phase 3E acceptance run because the endurance harness contained an over-strong runtime assertion about queue depth. The underlying distributed collection completed successfully after one worker stopped on that assertion.

## Topology and workload

Collectors:

- `hnl-01` / `phase3e-hnl-01`
- `kah-01` / `phase3e-kah-01`
- `tcou` / `phase3e-tcou`

Database target:

- `mak-db-02.bf4statusbot.com`
- `bf4_playerstats_test`

Frozen workload:

- 120 soldiers total
- 40 PC
- 40 PS4
- 40 Xbox One
- resource/lane: `detailed/background`
- feeder actionable target: 6
- global terminal-attempt ceiling: 120

The initial seed materialized exactly six pending, attempt-zero jobs. The remaining cohort was intentionally left unmaterialized so the run exercised the production bounded feeder repeatedly under concurrent consumption.

## Observed result

Final terminal event distribution was:

| Collector | Successes | Failures |
|---|---:|---:|
| `phase3e-hnl-01` | 43 | 0 |
| `phase3e-kah-01` | 43 | 0 |
| `phase3e-tcou` | 34 | 0 |
| **Total** | **120** | **0** |

The final Phase 3E queue contained zero rows. All three collector rows had `current_job_id = NULL`. The surviving Honolulu and Kahului workers stopped cleanly when the global 120-attempt ceiling was reached.

No 403/429/throttle signal was reported by the live workers.

## tcou harness stop

After 34 successful collections, `tcou` raised:

`RuntimeError: bounded queue depth exceeded Phase 3E target`

The worker's `finally` path still executed `stop_collector()`. Subsequent inspection showed tcou with no current job and a stopped/unknown heartbeat state, so the exception did not strand queue ownership.

The event ledger around the stop showed active concurrent progress on all three hosts:

- `12:15:51.773151Z` — tcou success, job 189
- `12:15:54.612225Z` — kah-01 success, job 191
- `12:15:54.645094Z` — hnl-01 success, job 190
- `12:15:56.800429Z` — tcou success, job 192
- `12:15:58.943251Z` — hnl-01 success, job 193
- `12:15:59.619437Z` — kah-01 success, job 194
- `12:16:04.131274Z` — hnl-01 success, job 195
- `12:16:04.587294Z` — kah-01 success, job 198

Honolulu and Kahului continued processing after tcou stopped and together drove the frozen run to the exact 120-attempt ceiling.

## Queue-depth semantic discovered by the run

The production bounded feeder serializes feeder passes with the transaction-scoped PostgreSQL advisory lock `bf4ps:phase2:detailed-feeder`. While holding that serialization point it measures actionable depth, computes only the required deficit, applies the global attempt budget, materializes bounded work, re-measures actionable depth, and raises if its own post-replenishment depth exceeds the target.

The Phase 3E endurance harness additionally performed an independent `safety_check()` before entering that serialized feeder operation. That check treated any instantaneous observation of actionable depth greater than 6 as a fatal invariant violation.

That harness assertion is too strong for the concurrent runtime model. Queue target 6 is a **serialized feeder replenishment invariant**, not a promise that every arbitrary concurrent database observer must always see cardinality <= 6. Collector claim/finalize activity and separately committed feeder transactions can interleave with an unsynchronized observer.

The production feeder did not raise its own `bounded feeder invariant violated: actionable depth exceeds target` exception during this run. The fatal exception came from the independent Phase 3E harness assertion.

Therefore this incident does **not** establish a production bounded-feeder defect. It establishes that the endurance harness must distinguish feeder-boundary enforcement from observational queue-depth telemetry.

## Unexpected degraded-operation evidence

The tcou stop unintentionally exercised three-to-two-host degradation. The result was useful:

- tcou stopped without stranded ownership;
- unrelated work continued on hnl-01 and kah-01;
- bounded replenishment continued;
- the global ceiling remained effective;
- the remaining frozen cohort converged to 120 terminal successes;
- the queue ended empty.

This is positive evidence, but it does not replace the frozen Phase 3E drain/restart/reclamation stages required by the design.

## Required correction before the next live run

The next harness revision must:

1. keep the production bounded feeder as the authority that enforces target depth at its serialized replenishment boundary;
2. stop treating an unsynchronized `actionable > target` observation as fatal;
3. preserve actionable-depth observations as telemetry, including the maximum observed depth and notices for observations above target;
4. retain all genuine hard-stop boundaries: frozen cohort containment, database/revision target, allowed collector ownership, and global attempt ceiling;
5. add regression coverage for the distinction between feeder enforcement and observational telemetry;
6. add a read-only global Phase 3E reconciliation before the next acceptance run.

## Acceptance disposition

This first 120-player run is **not** the final Phase 3E PASS.

It demonstrated successful sustained distributed collection and useful degraded operation, but exposed a harness semantics defect before the complete frozen Phase 3E lifecycle sequence was validated.

After documentation and harness correction, Phase 3E will use a new pristine 120-soldier 40/40/40 cohort for the next acceptance run. The completed first-run evidence must be preserved until reconciliation and documentation are complete.
