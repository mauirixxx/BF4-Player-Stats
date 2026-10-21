# BF4PS Phase 3E second endurance run

Status: **investigative run — production feeder concurrency semantic discovered**

Date: 2026-10-04 UTC

Design: `docs/phase3e-distributed-endurance-design.md`

Alembic head: `0003_request_gates`

## Purpose

Round two repeated the sustained three-host Phase 3E exercise with a new frozen 120-soldier cohort: 40 PC, 40 PS4, and 40 Xbox One soldiers. It retained the production bounded feeder, actionable target 6, hard global attempt ceiling 120, and 5-second per-egress request pacing.

The harness-side queue-depth assertion found in round one had already been converted to telemetry. Round two therefore specifically tested whether the same concurrency condition could appear at the production feeder boundary.

## Observed result

All 120 terminal attempts completed successfully with zero collection failures.

- `phase3e-tcou`: 64 successes
- `phase3e-hnl-01`: 14 successes before feeder stop
- `phase3e-kah-01`: 42 successes before feeder stop
- total: 120 successes, 0 failures

`tcou` reached the exact global 120-attempt ceiling and stopped cleanly with actionable depth 0 and a maximum observed actionable depth of 6.

Both remote workers independently observed a transient actionable depth of 7 and then stopped inside the production bounded feeder with:

`RuntimeError: bounded feeder invariant violated: actionable depth exceeds target`

The important result is that round two reproduced the concurrency condition *inside the production feeder*, disproving the narrower round-one interpretation that the production feeder's final `actionable_after <= target_depth` assertion was safe merely because feeder passes are serialized.

## Corrected queue-depth semantic

The production feeder serializes feeder passes with the transaction-scoped PostgreSQL advisory lock `bf4ps:phase2:detailed-feeder`. That lock prevents two feeder passes from simultaneously calculating a deficit and materializing bootstrap work.

It does **not** serialize collector claim/finalize state transitions against the feeder transaction.

Therefore `target_depth = 6` is a **replenishment target**. It controls how much new work a serialized feeder pass is allowed to materialize from the depth it observes. It is not a globally exclusive instantaneous cardinality invariant across all collector and feeder transactions.

A final depth observation above target can therefore be legitimate concurrency telemetry even when the feeder itself materialized no more than its calculated deficit. Treating that observation as a fatal production invariant caused the hnl-01 and kah-01 worker exits in round two.

## Patch disposition

The production feeder is patched so that:

1. the advisory transaction lock remains unchanged;
2. actionable depth is still measured before replenishment;
3. deficit remains `max(0, target_depth - actionable_before)`;
4. explicit cohort and maximum-attempt safety boundaries remain unchanged;
5. materialization still selects only eligible never-attempted soldiers and preserves queue uniqueness;
6. `actionable_after` remains returned as telemetry;
7. a transient `actionable_after > target_depth` no longer raises a fatal exception.

Regression coverage simulates a feeder observing depth 5 before replenishment and depth 7 afterward due to concurrent queue-state movement. The expected behavior is to return the final depth as telemetry rather than fail.

No schema change is required.

## Acceptance disposition

Round two is not the final Phase 3E PASS because two workers exited on the now-confirmed production feeder assertion defect.

It is nevertheless strong evidence for the distributed collector architecture: the frozen workload still converged to exactly 120 successful terminal attempts with no collection failures, and the global ceiling remained effective.

After the feeder patch is deployed and the test suite is green on all three hosts, Phase 3E should use another pristine 120-soldier 40/40/40 cohort for round three. Round three should specifically verify that transient actionable depth above the replenishment target is non-fatal while all hard experiment boundaries remain enforced.
