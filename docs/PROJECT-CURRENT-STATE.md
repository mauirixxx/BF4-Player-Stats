# BF4 Player Stats — Current State

**Last reconciled:** 2026-10-08  
**Status:** Stage 9C **HOLD / NOT AUTHORIZED**. This is a living navigation checkpoint, not an activation instruction.

## How to resume

1. Read this document and `docs/phase5b-stage9c-readiness-review.md` before planning new work.
2. Read `docs/database-schema-reference.md` **and all current Alembic migrations** before writing SQL, persistence, or integration tests. Migration head documented as `0004_stage9c_supervision_runs`; confirm the live target revision independently.
3. Compare the intended task against existing scripts, tests, and branches before implementing. Treat recorded PASS evidence as historical unless rerun.
4. Prefer committing changes to a dedicated GitHub branch for operator review and live testing.
5. Update this checkpoint with each meaningful validated milestone, explicitly distinguishing **implemented**, **tested**, **operator verified**, and **still open**.

## Repository and branches

- Repository: `mauirixxx/BF4-Player-Stats`.
- Main implementation reference at this checkpoint: `feature/phase5a-cost-cohort` (GitHub branch SHA `595dbf78171d6d45cfc77f398b86def6f63651c3`).
- Current documentation and validation development branch: `test/stage9c-admission-concurrency`. Do not mistake branch creation for a successful integration test.
- The repository `main` branch is **not** the latest Stage 9C implementation branch.

## Frozen operational policy

- Aggregate automatic background limit: **1,296 physical starts in any rolling hour**, across eligible resources and collectors.
- Per-egress pacing: minimum **5 seconds** between requests.
- Accepted Stage 9B materialization cutover: `2026-10-08T00:47:34.757784+00:00`.
- Exclusive Stage 9B event boundary: `11558`.
- Cutover and event boundary **do not reset** the rolling budget.
- Stage 9C supervisor activation, materializer restart, collector launch, migrations, and real systemd stop tests require explicit separate operator approval.

## Completed work and recorded evidence

The authoritative detailed evidence is `docs/phase5b-stage9c-readiness-review.md`, including later addenda that supersede its earlier historical gate descriptions.

- Offline suite: **406/406 PASS**, last recorded on mak-01. This is prior operator evidence, **not a run on this branch**.
- Isolated PostgreSQL scratch: **22 checks PASS** across rolling budget, `inspect()`, abort/drain, and fault paths.
- Actual watchdog `main()` isolated PostgreSQL integration: **4 scenarios PASS**, including rolling-hour 1,297 overage and committed fenced abort/drain.
- Independent read-only Stage 9C checkpoint scratch: **3 checks PASS**, with ledger completeness explicitly **UNVERIFIED**.
- Phase 3A queue concurrency and Phase 3B lease-fencing harnesses already exist; they are not proofs of Stage 9C aggregate production admission at its boundary.
- `bf4ps/background_service.py` implements transaction-advisory-lock admission with rolling start events plus unstarted claimed/running reservations.
- Detailed, weapons, and vehicles collector source paths have been inspected for durable pre-HTTP attempt-start events; this is source evidence, not a concurrent execution proof.
- The Stage 9C watchdog's cross-boundary rolling-hour logic and persisted supervision `started_at` handling have been corrected and scratch-tested. Historical Stage 9B checkpoint reporting is **not** sufficient for Stage 9C.

## Open gates (do not silently mark closed)

1. Independently verify intended database's live schema and Alembic revision; any migration needs an explicit plan and approval.
2. Complete remaining failure/DB-loss and real supervision safety validation. Prior watchdog `main()` scratch tests have closed **part**, not all, of this gate.
3. Verify real host-local guard/systemd shutdown and in-flight request behavior safely before a real fleet launch.
4. Prove aggregate production scheduler admission under independent PostgreSQL transaction races; investigate reservations, lease reclaims, retries, and cross-resource starts. Verify physical-start ledger completeness separately.
5. Run read-only deployment preflight for collector identities, distinct egresses, writable primary, queue, retry debt, and unexpected processes.
6. Obtain explicit operator authorization for any Stage 9C six-hour trial, materializer restart, or collector launch.

## Current development task

**Stage 9C admission concurrency proof**, design: `docs/stage9c-admission-concurrency-validation.md`.

Reuse `scripts/phase3a_concurrent_claim_integration.py`, `scripts/phase3b_lease_fencing_integration.py`, `scripts/phase5b_background_service_db_validate.py`, and the Stage 9C scratch harnesses as references. Their historical revision pins and target guards differ; **do not run or repoint them unchanged**. Any new harness must use the existing strictly allowlisted disposable Stage 9C database, verify host/IP/role/revision before writes, avoid outbound HTTP, and clean only owned fixtures.

The first two commits on the current branch were documentation and offline safety-contract tests; **no concurrency harness execution has yet been claimed**.

## Change log

- **2026-10-08:** Established living checkpoint from current repository and readiness evidence. Explicitly scoped remaining concurrency work to avoid duplicating Stage 9C rolling-budget, watchdog, read-only checkpoint, and earlier Phase 3 queue/lease proofs.
