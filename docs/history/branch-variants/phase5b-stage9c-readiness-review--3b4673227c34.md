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

### Watchdog entrypoint regression evidence (mak-01)

Commit `aed72e7` corrected a production-code wiring gap: watchdog `main()` now passes the persisted lease `started_at` into `inspect(supervision_start=...)` instead of silently defaulting to the Stage 9B cutover. The immutable cutover and exclusive event boundary remain unchanged. Commit `8d952b4` added nine offline, mocked-`main()` tests covering armed renewal, abort/drain invocation, dry-run nonmutation, database failure, lease expiry, and CLI fail-closed validation. **Full suite: 376 passed, 0 failed** on mak-01.

These tests do not prove real database transaction rollback/commit behavior inside `main()`, the fallback abort branch, or physical systemd guard termination. Gate 2 remains **open** until those paths receive targeted fault-injection evidence; gate 3 remains **open**. No live activation authorized.

### Additional fail-closed control-flow tests (mak-01)

Commit `4edb469` added five watchdog `main()` fault-injection cases: atomic drain failure rolls back before separate sticky-abort fallback; fallback failure returns unhealthy; abort failure prevents drain/renewal; renewal failure rolls back; successful abort/drain commits in the fake transaction model. Commit `2a003b1` added seven local-guard `main()` cases covering healthy checks, exact allowlisted stop targets for tcou/hnl-01/kah-01, dry-run, stop failure and unsupported host. Commit `73c135a` corrected a **test-isolation defect**: the initial guard test mocked `subprocess.run` too late to override the function's captured default runner, causing real `systemctl stop` attempts on mak-01. They failed with `Interactive authentication required`; no successful stop was observed. The corrected test explicitly injects a fake runner through `stop_units` and avoids systemctl execution.

After correction, the **full offline suite passed 388/388** on mak-01. This validates mocked entrypoint behavior only; it does not verify actual systemd process termination or durable PostgreSQL transaction outcomes. Gates 2 and 3 remain open pending the appropriate isolated integration and operator checks. **HOLD remains in force.**

### Persisted supervision timestamp validation (mak-01)

Commits `3f7ca8c` and `bcda09c` make armed watchdog `main()` reject absent, non-datetime, or timezone-naive persisted `started_at` rather than silently falling back to the Stage 9B materialization cutover. Three new offline regressions passed; **full suite 391/391 PASS** on mak-01. The real PostgreSQL `main()` entry path and actual systemd termination remain separate unverified gates.

### Actual watchdog main() — isolated PostgreSQL integration (mak-01 → mak-db-02)

Commits `26ea886` and `698419f` added and corrected `scripts/phase5b_stage9c_watchdog_main_scratch.py`. The harness enforces the dedicated scratch URL allowlist, verifies live database/user/IP/revision and empty real collector/run ledgers, shadows collectors/events/jobs using session-local PostgreSQL TEMP tables, and creates only disposable Stage 9C supervision runs. It invokes the **actual** watchdog `main()` with a connection-bound SQLAlchemy engine facade, while preventing network collection, real systemd operations and production DB access.

The first execution passed healthy renewal but encountered the expected schema constraint `uq_stage9c_one_active_run` when the harness attempted a second simultaneous active run. The harness was corrected to delete its own completed healthy run before the next scenario. The subsequent `--execute` run passed **4/4**: healthy inspection/lease renewal, rolling-hour 1,297-start overage triggering committed abort plus three TEMP collector drains, identity-drift rollback followed by committed sticky abort with fleet undrained, and scratch ledger cleanup. Critical abort/fallback logs were deliberately injected and expected.

This materially strengthens **gate 2**: actual `main()` transaction and fallback paths have been exercised against isolated PostgreSQL. Remaining gate-2 concerns include broader failure coverage and DB-loss/lease-expiry behavior in real supervision; **gate 3 physical shutdown** is still unproven for real workloads. **Decision: HOLD / NOT AUTHORIZED.**

### Historical checkpoint-audit reconciliation (design review)

The Stage 9B `scripts/phase5b_step9_checkpoint_audit.py` is still pinned to revision `0003_request_gates` and calculates its rolling maximum only over post-boundary starts. Its PASS is **not sufficient** to establish Stage 9C cross-boundary rolling-budget compliance. The Stage 9C watchdog has corrected bounded time-window logic and separate persisted supervision start. Design and required independent Stage 9C read-only audit contract are now recorded in `docs/phase5b-stage9c-rolling-budget-boundary-audit.md`; historical checkpoint script intentionally unchanged. This is **not** proof of live ledger completeness, and gate 4 remains open.

### Independent read-only checkpoint — isolated PostgreSQL evidence

Commit `818ccd0` added `scripts/phase5b_stage9c_checkpoint_scratch.py`. Against the strictly allowlisted scratch database, the integration passed three checks: cross-supervision 1,297-start observed budget violation, 1,296-start observed compliance with ledger completeness still explicitly UNVERIFIED, and PostgreSQL rejection of an attempted DELETE inside the audit's READ ONLY transaction. Disposable supervision run and session-local TEMP event rows were cleaned. The full offline suite on mak-01 remained **406/406 PASS**.

This validates the query and read-only contract against scratch PostgreSQL; it does **not** validate complete physical-start evidence, production scheduler accounting, or a live main-test database. Gate 4 remains open and the six-hour trial is still HOLD.

### Scheduler admission and physical-start ledger source audit

Read `bf4ps/production_scheduler.py`, `bf4ps/background_service.py`, `bf4ps/request_gate.py`, `scripts/bf4ps_production_collector.py`, and the detailed collector's physical-start path. The materializer enqueues work, not HTTP. The production collector sets `enforce_production_budget=True`; `claim_production_background_job` serializes admissions with PostgreSQL transaction advisory lock `bf4ps:phase5b-background-service`, counts last-hour `collection_attempt_started` events plus outstanding claimed/running reservations with no start event, and enforces the aggregate 1,296 limit. The egress request gate separately reserves spacing and commits before waiting.

The detailed collector validates a still-owned running lease under row lock and commits a `collection_attempt_started` event in its own transaction **before** calling `fetch_detailed_stats`. A failed start insert prevents reaching that HTTP call on this inspected path. This is useful source-level evidence, **not** a concurrency proof for all resources or a guarantee that a persisted start always corresponds to an actual HTTP request.

**Unresolved safety question:** reservation accounting uses a rolling event window plus currently claimed/running jobs; when reservations age out or leases are reclaimed, prove that delayed requests cannot exceed the strict physical-start ceiling. Independently inspect weapons and vehicles paths, duplicate/replay protection, and the source of event timestamps. Also note the admission SQL uses `occurred_at >= now() - interval '1 hour'`, while the watchdog uses strict expiration; document any conservative boundary differences. Gate 4 remains open; no rollout authorization.

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
