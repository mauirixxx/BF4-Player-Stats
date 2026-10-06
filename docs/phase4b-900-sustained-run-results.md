# Phase 4B 900-player sustained distributed collection — acceptance record

Status: **PASS — eventual convergence after automatic retry recovery**

Date: 2026-10-06 UTC

## Purpose

Phase 4B scaled the proven Phase 4A sustained distributed detailed-statistics collection workload from 90 to 900 previously untouched PC soldiers while retaining the same three physical collectors, production detailed collection path, PostgreSQL-coordinated queue, and per-egress request gates.

The run also produced useful transient Battlelog normalization failures. Those failures were automatically retried and all affected soldiers subsequently converged to successful persisted state. This recovery behavior is part of the Phase 4B acceptance evidence.

## Frozen execution contract

- Collectors: `phase3e-hnl-01`, `phase3e-kah-01`, `phase3e-tcou`
- Physical hosts: `hnl-01`, `kah-01`, `tcou`
- Resource: `detailed`
- Lane: `background`
- Frozen cohort size: 900 PC soldiers
- Target actionable queue depth: 6
- Global initial terminal-attempt ceiling: 900
- Per-egress request spacing: 5.0 seconds
- Production detailed collection path used by all three workers
- PostgreSQL request gates used for outbound pacing
- Safety boundary for HTTP 403/429 and `battlelog_throttle`

The frozen cohort was committed in `scripts/phase4b_cohort.py` as commit `527a0ba` (`test: freeze Phase 4B 900-player cohort`). The sustained worker was committed as `scripts/phase4b_worker.py` in commit `1513f3a` (`test: add Phase 4B 900-player sustained worker`).

## Preflight

The Phase 4B preflight passed before ignition. It established:

- exactly 900 frozen PC soldiers;
- all 900 detailed states pristine (`never_attempted`);
- no frozen-cohort detailed jobs existed;
- no foreign detailed/background jobs existed;
- the three stable collectors were exact, enabled, undrained, and idle;
- no active collector owned a job;
- all three required request gates existed;
- no prior Phase 4B terminal events existed; and
- no Battlelog requests or database writes were performed by the preflight.

Starting detailed-stat persistence counters were 887 current rows and 887 history rows. The pre-run collection-event maximum was event 904.

## Initial sustained run

All three workers were launched concurrently against the same database and frozen cohort.

Initial terminal-attempt distribution:

| Collector | Host | Attempts | Initial successes | Initial temporary failures |
|---|---|---:|---:|---:|
| `phase3e-hnl-01` | `hnl-01` | 300 | 296 | 4 |
| `phase3e-kah-01` | `kah-01` | 299 | 295 | 4 |
| `phase3e-tcou` | `tcou` | 301 | 295 | 6 |
| **Total** | | **900** | **886** | **14** |

All three workers remained operational and stopped cleanly after the global 900-attempt ceiling was reached. There were zero residual cohort detailed jobs after the initial run.

The initial Phase 4B event span was `905..1804`, exactly 900 contiguous terminal events following the Phase 4A closure.

## Initial post-run audit

The first read-only post-run audit correctly identified that the initial 900 attempts were not all successful:

- 900 terminal attempts;
- 886 successes;
- 14 temporary failures;
- 886 cohort states initially observed as `success` and 14 as `never_attempted` within the original acceptance view;
- 886 current rows and 886 history rows represented by that initial audit;
- zero residual cohort jobs;
- zero HTTP 403/429/throttle events; and
- all three collectors participated and owned no current job after stopping.

Accordingly, the original strict "all 900 initial terminal attempts succeeded" acceptance condition was **INCOMPLETE**, not a successful first-pass 900/900 result.

A separate collector-registry identity failure reported by the first audit was an audit bug rather than a runtime failure. PostgreSQL UUID values were being compared to stringified Python UUIDs. Commit `4289692` (`test: fix Phase 4B collector UUID audit`) corrected that verifier defect.

## Failure forensics

Read-only forensic reconciliation found exactly 14 initial detailed failures. All 14 shared one fingerprint:

- result: `temporary_failure`
- HTTP status: `None`
- error class: `battlelog_normalization`
- error message: `generalStats is missing or is not an object`
- retry delay metadata: 300 seconds

The failures occurred across all three independent collectors rather than being isolated to one host or egress. They were concentrated early in the sustained run, with additional occurrences later in the initial workload.

No HTTP 403 or 429 response was associated with these failures. The evidence supports classifying them as transient unusable Battlelog payloads reaching the normalization layer, not request throttling and not a collector crash.

## Automatic retry recovery

The most important Phase 4B result is that the 14 failures were not permanent casualties.

For every one of the 14 affected soldiers, forensic reconciliation later found:

- collection state `success`;
- a populated `last_success` timestamp;
- `consecutive_failures=0`;
- no remaining state error class or error message;
- a current detailed-stat row; and
- one detailed history row.

The observed recovery timestamps are approximately five minutes after each corresponding temporary failure, matching the recorded `retry_after_seconds: 300` policy.

Examples include:

- soldier 504 / `walkerson420`: temporary failure at 06:18:48 UTC, later success at 06:23:58 UTC;
- soldier 505 / `QWQ10011`: temporary failure at 06:18:49 UTC, later success at 06:24:00 UTC;
- soldier 506 / `HL001DZ`: temporary failure at 06:18:52 UTC, later success at 06:24:02 UTC;
- soldier 585 / `Blurrr666`: temporary failure at 06:21:03 UTC, later success at 06:26:13 UTC; and
- soldier 760 / `MocarnaSardynka`: temporary failure at 06:26:17 UTC, later success at 06:31:27 UTC.

Thus the original 900-event span describes the first attempt for each frozen soldier, but it does **not** describe the final lifecycle outcome of the cohort. The authoritative final outcome must include the automatic retry/recovery state.

## Final acceptance interpretation

Phase 4B therefore has two distinct measurements that must not be conflated:

1. **First-pass outcome:** 886/900 successful, with 14 temporary Battlelog normalization failures.
2. **Eventual lifecycle outcome:** all 14 temporary failures subsequently recovered automatically and persisted successfully, yielding 900/900 successful frozen soldiers.

This is stronger distributed-worker evidence than an entirely clean first pass would have provided. The run exercised the failure classification, delayed retry, cross-node distributed work machinery, state cleanup, and persistence path under sustained three-node load without manual repair of the affected soldiers.

Acceptance evidence:

- exact frozen cohort of 900 soldiers — **PASS**
- exactly 900 initial terminal attempts — **PASS**
- contiguous initial event span `905..1804` — **PASS**
- all three physical collectors participated — **PASS**
- initial successes: 886 — **OBSERVED**
- initial temporary failures: 14 — **OBSERVED**
- all 14 failures share the expected normalization fingerprint — **PASS**
- all 14 were scheduled with 300-second retry metadata — **PASS**
- all 14 later converged to `success` — **PASS**
- all recovered soldiers have current persistence — **PASS**
- all recovered soldiers have history persistence — **PASS**
- recovered states have zero consecutive failures and no remaining error — **PASS**
- zero HTTP 403/429/throttle events — **PASS**
- zero residual cohort detailed jobs — **PASS**
- collectors stopped without owned current jobs — **PASS**
- collector-registry UUID verifier defect corrected — **PASS**

**PHASE 4B FINAL LIFECYCLE OUTCOME: PASS — 900/900 EVENTUAL SUCCESS**

## Conclusion

Phase 4B demonstrates that BF4PS can sustain a tenfold workload increase over Phase 4A across three physical collectors while preserving bounded distributed queue behavior and per-egress request pacing. More importantly, the run encountered real transient Battlelog payload failures and recovered from them automatically.

The system rejected unusable `generalStats` payloads rather than persisting malformed detailed statistics, classified the condition as temporary, applied the 300-second retry policy, and later persisted successful current/history data for every affected soldier. No collector crashed, no residual queue work remained, and no HTTP 403/429/throttle event was observed.

The frozen 900-player cohort therefore finished at **900/900 eventual successful collection**, with the 14 temporary failures retained as valuable evidence that the retry/recovery lifecycle works under sustained distributed load.
