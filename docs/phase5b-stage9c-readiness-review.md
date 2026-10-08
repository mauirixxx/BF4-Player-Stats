# Stage 9C — six-hour trial pre-activation readiness review

**Evidence recorded:** 2026-10-08 (operator tcou outputs). **Decision: HOLD / NOT AUTHORIZED.** This document records completed checks and unresolved gates; it does not authorize migrations, collector or materializer starts, Battlelog requests, or real systemd changes.

## Frozen policy and reference points

- Stage 9B accepted materialization cutover: `2026-10-08T00:47:34.757784+00:00`.
- Exclusive Stage 9B event boundary: `11558`. Neither value may be regenerated for Stage 9C.
- Aggregate background ceiling: **1,296 physical starts in any rolling hour**, across all eligible resources and collectors. Boundary is an audit fence, **not a budget reset**. Exactly 60 minutes apart does not share the same strict rolling window.
- Per-egress minimum request interval: five seconds. Preserve frozen fairness, retry, and prospective materialization policies.
- Do not clear accepted Stage 9B temporary failure debt or historical evidence merely to produce a clean audit.

## Verified evidence and limits

| Evidence | Operator result | What it does *not* establish |
|---|---|---|
| Offline Stage 9C rolling-budget, fault-injection and supervision suite | **29/29 PASS** on tcou, commit `61d9594` | Real process shutdown or live DB behavior |
| Dummy systemd dependency/guard exercise | **9/9 PASS** across tcou, kah-01 and hnl-01 | Real collector shutdown or newly installed production units |
| Isolated scratch abort/drain fault injection | **PASS** on tcou, commit `59f3a1f`; normal commit, drift rollback + sticky fallback, stale owner/generation, cleanup | Watchdog main loop, physical guard shutdown |
| Rolling-budget SQL via scratch TEMP event ledger | **PASS** on tcou, commit `6a4a9f0`: 1,297 rejected, 1,296 accepted, 60-minute cutoff, pre-cutover-only peak excluded, eligibility filtering, missing-table query failure propagated, TEMP cleanup | Real scheduler enforcement, missing physical-start events, actual main DB ledger |
| Full `inspect()` PostgreSQL scratch path | **PASS** on tcou, commit `ecfabdb`: overage flagged, 1,296 accepted, start/terminal reconciliation, SQL error propagation, TEMP isolation | Lease/abort main process control flow |
| PostgreSQL budget violation → fenced abort → fleet drain | **PASS** on tcou, commit `bc24d87`: 1,297 overage, durable abort reason, three TEMP collectors drained, terminal replay/foreign owner rejected, disposable run cleanup | Actual watchdog `main()` execution, real fleet stop, guard expiry on host |

The scratch integration target is the explicitly allowlisted `bf4ps_scratch_stage9c_integration` at `192.168.10.78`, with user `bf4ps_stage9c_integration` and Alembic `0004_stage9c_supervision_runs`. The test harnesses require explicit `--execute`, refuse unsafe targets and nonempty real collector/run registries, use PostgreSQL TEMP shadows for collector/event/queue data, and clean disposable supervision rows. They do **not** constitute an upgrade of `bf4_playerstats_test`.

**Observed cleanup:** `PASS: scratch supervision ledger cleaned; TEMP tables session-scoped`. The budget harness also reported `public.collection_events` had zero rows on scratch. This does not prove anything about the main test database's ledger.

## Additional verification — 2026-10-08, mak-01

The isolated checkout on mak-01 was updated to feature branch commit `23fc099`. The full offline suite completed **367 passed, 0 failed**. The prior 15 failures were outdated Stage 9C test fixtures: three local-guard calls omitted the now-required run ID, and twelve watchdog cases supplied obsolete Alembic revision `0003_request_gates`. The fixtures were aligned with revision `0004_stage9c_supervision_runs`; an additional regression verifies that the local guard refuses a missing supervision lease. Test-only commits: `5e88d8b`, `23fc099`.

With explicit `--execute`, the four PostgreSQL scratch harnesses were rerun from mak-01 against the allowlisted scratch target on mak-db-02:

- Rolling budget: **10 PASS**, including pre-supervision saturated trailing hour, exact-hour expiry, and pre-supervision peak expiry without new starts (commit `e2ef1ee`).
- Complete `inspect()`: **4 PASS**.
- Budget violation to fenced abort/drain: **4 PASS**.
- Fenced abort/drain fault paths: **4 PASS**, including the intentionally injected incomplete-drain warning.

All **22 scratch checks passed**. TEMP shadow data and disposable supervision rows were cleaned; the rolling-budget harness reported persistent `collection_events` unchanged at zero rows. No real collector/materializer, production migration, or Battlelog request was initiated. These results strengthen isolated PostgreSQL behavior evidence but **do not** demonstrate watchdog `main()` end-to-end, real systemd termination, or live fleet readiness.

**Decision remains HOLD / NOT AUTHORIZED.** The six open gates below still require explicit resolution. For gate 4, the temporal-anchor design decision is now recorded: immutable Stage 9B cutover is the materialization/audit fence, while persisted Stage 9C `started_at` anchors supervision; the rolling budget must include pre-supervision physical starts in its trailing-hour context. Remaining gate-4 audit and scheduler verification are not waived.

## Open gates — no activation before resolution

1. **Production database/schema:** Stage 9C supervisor requires revision `0004_stage9c_supervision_runs`; last recorded main test DB preflight was `0003_request_gates`. Independently inspect live revision and schema against the documented reference, agree on maintenance/rollback plan, and obtain explicit approval before applying any migration.
2. **End-to-end watchdog main() and guard behavior:** The last harness exercised `inspect()`, `abort_owned_run()` and `drain_fleet()` in the same transaction but **did not run `main()`**. Validate CLI validation, lease ownership and expiration, main-loop exception/rollback, sticky abort fallback, and dummy-only host-local termination. The previous dummy-systemd 9/9 result is complementary.
3. **Real fleet shutdown contract:** DB `drained=true` blocks new claims; it does not kill in-flight HTTP or OS processes. Verify each real host's guard/service dependencies, local stop behavior and response to DB loss before any real collector start.
4. **Rolling-budget temporal anchor and evidence:** The watchdog currently scans from the frozen Stage 9B cutover minus one hour, then evaluates windows ending at starts at/after that cutover. Before Stage 9C activation, decide whether the **Stage 9B cutover** is the correct start for the Stage 9C six-hour supervision interval; do not silently substitute a new materialization cutover or reset the budget. Reconcile `scripts/phase5b_step9_checkpoint_audit.py` (historically event-boundary-scoped) with the corrected watchdog query, and inspect scheduler enforcement. Explicitly address missing/incomplete ledger evidence and any time/query growth constraints.
5. **Deployment preflight:** Recheck all three frozen collector identities, distinct egresses, DB writable primary/revision, no unexpected running collectors/materializers, clean queue ownership, throttle/persistence anomalies, and retained Stage 9B retry debt. Verify deployment-specific connectivity without triggering a collection request.
6. **Operator control and authorization:** Confirm coordinated fleet-wide emergency stop, rollback procedure, six-hour monitoring/audit checkpoints and separate explicit operator authorization for Stage 9C materializer restart (using the SAME frozen cutover) and three-egress collector launch.

## Recommended next safe work

- Audit the actual watchdog `main()` entry path and host-local guard wiring against the written supervision contract, then add **dummy-only** integration checks as necessary.
- Reconcile Stage 9C supervision timing versus the immutable Stage 9B materialization cutover **in design first**, including historical rolling-hour audit scope and bounded query behavior.
- Update stale future-tense portions of `docs/phase5b-stage9c-watchdog-lease-design.md` and `docs/phase5b-stage9c-rolling-budget-boundary-audit.md` by linking to this evidence, without rewriting the historical decision record.
- Conduct read-only preflight on the main test DB only after confirming the approved operator command; no migration or activation implied.

**Decision:** HOLD. Passing scratch tests validate important safety primitives but do not authorize the six-hour trial.
