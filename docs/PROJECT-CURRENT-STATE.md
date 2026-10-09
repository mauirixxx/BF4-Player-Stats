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

## Historical milestone index (repository-evidenced)

This is a **navigation index**, not a replacement for original acceptance records. Historical documents can contain earlier STOP/HOLD states that were superseded by later implementation; always consult the latest dated acceptance and current source. PASS means **recorded in the linked document**, not independently rerun during this checkpoint update.

| Phase | Recorded milestone and evidence | Authoritative repository record |
|---|---|---|
| Foundation | Battlelog source reconnaissance, retention policy, database and operational schema, collector architecture/registry, discovery contracts. **Design documented**; implementation/acceptance varies by component. | [Battlelog sources](battlelog-data-sources.md), [schema reference](database-schema-reference.md), [collector architecture](collector-architecture.md), [BF4SW discovery](bf4sw-discovery.md) |
| Phase 1 | Detailed stats fetched and persisted for PC, PS4 and Xbox One with HTTP 200, valid queue finalization and canonical history behavior. **Live cohort PASS recorded.** | [Multiplatform live validation](phase1-multiplatform-live-validation.md), [failure/recovery validation](phase1-failure-recovery-live-validation.md) |
| Phase 2 | Bounded single-node feeder/runtime completed 10/10 detailed jobs across repeated replenishment cycles. **Live PASS recorded.** Other drain/recovery checks have separate records. | [Sustained runtime](phase2-sustained-runtime-live-validation.md), [bounded feeder](phase2-bounded-feeder-live-validation.md), [drained runtime](phase2-drained-runtime-live-validation.md) |
| Phase 3A–3C | Concurrent queue claims, lease fencing and operator lifecycle each have dedicated validation records. **Do not conflate queue exclusivity with Stage 9C aggregate admission.** | [Concurrent claims](phase3a-concurrent-live-validation.md), [lease fencing](phase3b-lease-fencing-validation.md), [operator lifecycle](phase3c-operator-lifecycle-validation.md) |
| Phase 3D | Three physical hosts competed for one PostgreSQL queue: 36/36 successful detailed collections, 12 attributed to each collector, no 403/429, clean queue and stops. **Live distributed PASS recorded.** | [Three-host validation](phase3d-three-host-validation.md) |
| Phase 3E | Abrupt-loss recovery, cross-host reclamation, and final clean-stop closure documented. **Final clean-stop PASS recorded; consult the separate final acceptance evidence before claiming whole-phase closure.** | [Final clean-stop closure](phase3e-final-clean-stop-closure.md), [endurance records](phase3e-third-endurance-run.md) |
| Phase 4A | 90-soldier sustained distributed ramp with a dedicated acceptance record. | [Phase 4A results](phase4a-sustained-run-results.md) |
| Phase 4B | 900-player distributed sustained run: **PASS with automatic retry recovery** documented. | [Phase 4B results](phase4b-900-sustained-run-results.md) |
| Phase 4C | Multiplatform sustained detailed collection: **450 attempts** with one unresolved, lifecycle-valid Xbox retry at acceptance; audit **PASS**, not 450 successful unique soldiers. | [Phase 4C results](phase4c-multiplatform-sustained-run-results.md) |
| Phase 5A | Weapon/vehicle collection design, implementation census, weapon persistence integration contract, and live weapon probe records exist. **The original implementation census is historical and does not describe current code availability.** Do not claim complete full-stats cost characterization solely from these documents. | [Cost characterization design](phase5a-full-stats-cost-characterization.md), [implementation census](phase5a-implementation-census.md), [weapon persistence contract](phase5a-weapon-persistence-integration.md), [weapon probe](phase5a-live-weapon-probe-results.md) |
| Phase 5B Steps 7–8 | Accepted endurance: 3,888 physical starts and terminals, 3,864 distinct jobs, 24 retries, rolling-hour maximum 1,296, zero 403/429 and zero persistence failures. **Accepted evidence recorded.** | [Step 9 activation plan (accepted Step 7/8 evidence)](phase5b-step9-production-activation-plan.md), [Step 7 endurance plan](phase5b-step7-endurance-plan.md) |
| Phase 5B Stage 9B | Prospective materialization cutover accepted; immutable timestamp and event boundary are recorded above. Stage 9B historical audit does not certify Stage 9C cross-boundary budget. | [Production activation plan](phase5b-step9-production-activation-plan.md), [Stage 9C rolling-budget audit](phase5b-stage9c-rolling-budget-boundary-audit.md) |
| Stage 9C | Watchdog supervision, rolling-hour cross-boundary accounting, scratch integration and read-only checkpoint have substantial passing evidence. **Live six-hour trial remains HOLD.** | [Readiness review](phase5b-stage9c-readiness-review.md), [rolling-budget audit](phase5b-stage9c-rolling-budget-boundary-audit.md), [supervision design](phase5b-stage9c-systemd-supervision-design.md) |

### Evidence interpretation

- Original dated validation documents are retained as immutable historical records. Do not overwrite historical STOP/HOLD language to make the timeline appear uniformly successful.
- A **design**, **execution contract**, **source census**, **PASS test**, and **operator-approved activation** are different statuses. The index deliberately preserves these distinctions.
- Earlier harnesses often pin Alembic `0003_request_gates`; Stage 9C scratch uses `0004_stage9c_supervision_runs`. Never assume a historical command is safe against a newer database.
- Historical counts describe their frozen cohort or bounded experiment only; they are not live fleet health or current production metrics.

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

### Admission concurrency build checkpoint — 2026-10-08

- Commit `0008a37` adds `scripts/phase5b_stage9c_admission_lock_scratch.py`: two independent PostgreSQL connections, production advisory lock, production `_usage()`, synthetic 1,295→1,296 physical-start ledger transition, explicit scratch-target allowlist and exact event-marker cleanup.
- **Authored, not executed.** This probe checks lock/usage visibility, **not** actual `claim_production_background_job()` concurrent queue claims, reservation accounting, retries, or lease reclamation. It must not be described as the Stage 9C admission gate passing.
- Before operator execution, review failure-path cleanup, transaction timing/barrier strength, and strict scratch database emptiness; only run with explicit authorization against the allowlisted disposable database.
- Next: improve deterministic barrier assertions; then add a genuine multi-connection `claim_production_background_job()` test with valid scratch soldiers/collectors/jobs and verify resource/retry/reclaim behavior. Maintain Stage 9C HOLD.

- Commit `e637715` strengthens the unexecuted lock/usage probe: a loser-ready barrier and a third PostgreSQL connection's `pg_try_advisory_xact_lock` confirm that the winning transaction still holds the production advisory lock before release. It also refuses fixture cleanup after preflight rejection. **Not a production queue-claim proof and not run yet.**

- Commit `cbfb1a5` introduces `scripts/phase5b_stage9c_claim_race_scratch.py`, an **unexecuted** two-connection real `claim_production_background_job()` race at 1,295/1,296, with distinct weapons/vehicles jobs and synthetic FK-valid scratch fixtures. **Next required action:** code review and offline/static validation, especially fixture setup/partial-failure cleanup, before any `--execute` invocation. Then run only on the exact Stage 9C scratch target and record operator evidence. Retry/reclaim/start-event transition cases remain open. HOLD.

- Commit `ac52405` reviews the actual claim-race harness failure paths: cleanup count checks now run *inside* the cleanup transaction so mismatches roll back, and fixture seeding rechecks emptiness under a dedicated advisory lock. **Not executed.** The advisory fixture lock coordinates this harness only; other scratch scripts do not necessarily use it. Review isolation and crash-leftover behavior before operator execution. No Stage 9C gate closed.

- Commit `c10b512` source-reviews the actual race harness against `bf4ps/background_service.py` and migration `0001_initial_schema`: explicitly establishes the losing transaction and replaces optimization-sensitive `assert` checks with raised exceptions. **Source inspection only; no Python compile, pytest, or PostgreSQL execution claimed.** The new harness requires exclusive disposable Stage 9C scratch access, and crash-leftover fixtures require manual inspection rather than broad cleanup. Next operator gate: run offline compile/tests, then strictly allowlisted scratch execution and save exact output; keep HOLD.
