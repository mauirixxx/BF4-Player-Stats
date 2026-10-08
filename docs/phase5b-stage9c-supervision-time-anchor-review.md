# Stage 9C supervision time-anchor design review

**Status: design analysis; decision pending. No runtime changes or activation.**

## Separate concepts that must not be conflated

1. **Stage 9B materialization cutover:** `2026-10-08T00:47:34.757784+00:00`. Immutable for prospective materialization and event provenance. Do not regenerate.
2. **Stage 9B exclusive event boundary:** `11558`. Immutable scope fence for accepted post-boundary attempt/terminal and abort-event audits. Not a request-budget reset.
3. **Stage 9C six-hour supervision start/deadline:** a separate operator-authorized runtime interval, persisted in `stage9c_supervision_runs.started_at` and `deadline_at`. The scratch harness uses `transaction_timestamp()` for its synthetic six-hour deadline. Do not infer actual Stage 9C start from the old materialization cutover.
4. **Rolling-hour physical-start budget:** global cap of 1,296 starts in any rolling 60 minutes. Pre-Stage-9C starts still count when they fall within a window under inspection.

## Source behavior and unresolved risk

`scripts/phase5b_stage9c_watchdog.py::rolling_background_max` currently fetches all eligible starts since **Stage 9B cutover minus one hour** up to DB `now()`, evaluates windows ending at starts at/after Stage 9B cutover, and returns the largest count. This correctly handles crossing that specific cutover and passed scratch SQL tests. However, it does **not** establish that the Stage 9B cutover is an appropriate historical start for a later Stage 9C run.

As the gap grows, query size grows, and a historical Stage 9B overage (if one had occurred) could be treated as a current Stage 9C abort even when its rolling window has long expired. Conversely, a current budget at a time with no new start may be exhausted despite the returned historical peak being zero. The scheduler must independently enforce the global cap; a watchdog is not a replacement for admission control.

The Step 9 checkpoint auditor historically computed rolling maximum from events after the frozen event ID boundary; this is not independent proof of the cross-boundary global cap.

## Proposed design, not approved for implementation

- Preserve the immutable materialization cutover and event ID boundary for their existing functions.
- Define an explicit, DB-derived **Stage 9C supervision start** for monitoring and the six-hour deadline. The start must be recorded durably and tied to the fenced run, not inferred from an old cutover.
- Compute a rolling budget from eligible physical starts in a time-bounded interval: include at least one hour before supervision start, and evaluate all starts during supervision. Also inspect the **current** rolling-hour usage at every watchdog cycle, including when no new starts occur.
- Verify the required event evidence is complete and timestamps are trustworthy; absence of rows is not itself evidence of completeness.
- Bound query cost, align checkpoint reporting, preserve strict 60-minute cutoff, and test late/out-of-order timestamps.
- Do not modify frozen constants, restart materialization, migrate the main DB, or launch collectors as part of this review.

## Decision required before code

Should Stage 9C budget monitoring use the persisted supervision run's `started_at` as its trial-history anchor while retaining the frozen Stage 9B cutover and event ID for provenance? This is the recommended separation, but it changes the watchdog's audit window and requires explicit operator acceptance plus regression tests.

**Gate: HOLD.** See `docs/phase5b-stage9c-readiness-review.md`.


## Operator design approval and initial implementation — 2026-10-08

Operator approved separation of immutable Stage 9B provenance anchors from Stage 9C's persisted supervision start. Initial implementation commits `ff38d3c`, `b5e9dc1`, and `e31c241`:

- Armed watchdog `main()` obtains `started_at` from the fenced `require_guard_lease()` row and passes it to `inspect()` as `supervision_start`.
- Rolling budget scans one hour before the supervision start, not the Stage 9B cutover, when the new parameter is provided. The Stage 9B cutover and event boundary remain unchanged for reconciliation.
- The rolling function additionally evaluates the trailing hour at current DB time, even if no starts occurred after supervision began.
- Added offline tests for the distinct time anchor, pre-trial context, live trailing-hour overage without new trial starts, exact expiry, and historical expiration.
- Existing `inspect()` callers retain the old `cutover` fallback until their scratch harnesses are migrated to pass an explicit synthetic supervision start. This is a **temporary compatibility path**, not the intended armed runtime contract.

**Not yet operator-validated:** These commits require a fresh tcou offline regression run and an updated PostgreSQL scratch run. Historical query volume, timestamp consistency, missing ledger completeness and Step 9 checkpoint alignment remain open. Do not activate Stage 9C.
