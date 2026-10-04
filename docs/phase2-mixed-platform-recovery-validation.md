# Phase 2 mixed-platform scheduler recovery validation

Status: **live validation passed**

Date: 2026-10-04 UTC

Branch: `fix/phase2-feeder-actionable-depth`

## Purpose

Preserve the live failure and recovery evidence for the Phase 2 bounded feeder actionable-depth fix.

The original mixed-platform sustained run used a frozen 3/3/3 cohort across PC, Xbox One, and PS4:

- PC: soldiers 17, 18, 19
- Xbox One: soldiers 93, 94, 95
- PS4: soldiers 105, 106, 107

The run exposed a real scheduler defect after eight soldiers had completed successfully.

## Original failure evidence

The original live run ended with:

- jobs attempted: 9
- jobs succeeded: 8
- jobs failed: 1
- feeder passes: **4732**
- jobs materialized: **8**
- soldier 107 (`Midnighttoker760`, PS4): `never_attempted`

The prior eight soldiers were successful, while soldier 107 never received a materialized job.

The retained incident state was intentionally preserved rather than cleaned up so the fix could be tested against the exact failure condition that exposed it.

## Root cause and fix

The feeder's working-depth accounting could treat non-actionable work as satisfying the bounded queue target. That allowed the runtime to repeatedly execute feeder passes without materializing the remaining eligible soldier.

Commit `69f23d0` changed feeder depth accounting to scope the bounded depth to **claimable/actionable work**.

This was a scheduler fix, not a test-specific workaround.

## Preserved-state recovery preflight

Immediately before the recovery run, the read-only preflight confirmed:

- database: `bf4_playerstats_test`
- writable primary (`pg_is_in_recovery() = false`)
- Alembic head: `0003_request_gates`
- exact 3/3/3 mixed-platform cohort retained
- successful soldiers: 17, 18, 19, 93, 94, 95, 105, 106
- soldier 107: `never_attempted`
- soldier 107 detailed current row absent
- cohort detailed/background queue: empty
- outside-cohort detailed/background queue: empty
- no database writes
- no external requests

## Recovery test bounds

The recovery harness was deliberately constrained to:

- `target_depth = 1`
- `max_jobs = 1`
- `max_soldier_id = 107`
- frozen allowed cohort: 17, 18, 19, 93, 94, 95, 105, 106, 107

It refused to execute unless the preserved 8-success + soldier-107-never-attempted incident shape was still present and the detailed/background queue was empty.

## Live recovery result

The corrected scheduler produced:

- jobs attempted: **1**
- jobs succeeded: **1**
- jobs failed: **0**
- feeder passes: **1**
- jobs materialized: **1**
- stopped by control: false

Soldier 107 (`Midnighttoker760`, PS4) transitioned from `never_attempted` to `success` at `2026-10-04 06:31:00.184206+00:00`.

The prior eight successful soldiers retained their original successful collection timestamps and were not recollected.

Final validation passed for:

- exactly one feeder pass
- exactly one job materialized
- exactly one collection attempt
- frozen cohort boundary
- prior eight successes preserved
- collector clean stop
- soldier 107 collected successfully
- all nine mixed-platform soldiers successful
- cohort queue finalized

No cleanup was performed; the successful recovery evidence was intentionally retained.

## Before / after

The same retained incident changed from:

`4732 feeder passes -> 8 materialized jobs -> soldier 107 never attempted`

to:

`1 feeder pass -> 1 materialized job -> 1 attempt -> soldier 107 success`

This live recovery against the original preserved failure state validates that the actionable-depth fix resolves the scheduler starvation observed by the mixed-platform sustained runtime.

## Phase 2 conclusion

The bounded feeder/runtime path has now been exercised with live Battlelog collection across PC, Xbox One, and PS4, including successful recovery from the scheduler defect discovered during sustained mixed-platform operation.

This incident and recovery should remain part of the Phase 2 validation record before progressing to the next collector phase.
