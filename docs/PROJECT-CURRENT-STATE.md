# BF4 Player Stats — Current State

**Last reconciled:** 2026-10-09  
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

### Actual PostgreSQL claim-race execution — 2026-10-08 (operator evidence)

- Host: `tcou`, isolated checkout `/opt/bf4ps-stage9c-validation`, branch `test/stage9c-admission-concurrency`, commit `821dfb5`; original `/opt/bf4-player-stats` checkout was not modified.
- Before execution: allowlisted scratch database `bf4ps_scratch_stage9c_integration` on `mak-db-02.bf4statusbot.com` (`192.168.10.78`), role `bf4ps_stage9c_integration`, writable primary, Alembic `0004_stage9c_supervision_runs`, five relevant tables empty.
- On `tcou`: harness compiled; 6/6 targeted Stage 9C contract tests and 412/412 full offline tests PASS; working tree clean.
- Direct script-path invocation failed with `ModuleNotFoundError: No module named 'scripts'` before database execution. **Working invocation:** `.venv/bin/python -m scripts.phase5b_stage9c_claim_race_scratch --execute` from repository root.
- Actual scratch PostgreSQL result, exit 0: `PASS: real production claim at 1295 reserves final slot`; `PASS: independent competing vehicles claim denied at 1296`; `PASS: committed reservation and lease ownership reconciled`; `Battlelog requests: 0`; `PASS: exact scratch fixture cleanup`.
- Scope: **one successful two-transaction, cross-resource production claim boundary test** with reservation and ownership assertions. Does **not** establish all retry, reclaim, reservation-to-start, rollback, physical-start completeness, one-hour boundary, or systemd/host-local safety cases. Stage 9C production six-hour trial remains **HOLD** pending remaining gates and explicit operator authorization.

- Post-run independent operator read-only check on `tcou`: `collectors=0`, `soldiers=0`, `collection_jobs=0`, `collection_events=0`, `stage9c_supervision_runs=0`; `PASS: Scratch database clean after claim race`. This verifies cleanup separately from the harness's own cleanup assertion.

## Stage 9C admission gate checkpoint — 2026-10-09 (operator-verified)

**Status: T1–T3 CLOSED; T4 OPEN; T5 OPEN; O1–O4 OPEN; Stage 9C production HOLD / NOT AUTHORIZED.** This checkpoint supplements the earlier 2026-10-08 admission-race record and does not change historical acceptance.

- **T1 (global rolling-budget, cross-resource starts/retries): CLOSED** per subsequent scratch validation record; do not confuse this with T5 physical-start ledger completeness.
- **T2 (duplicate physical-start prevention): CLOSED** per scratch concurrent/sequential rejection and accepted attempt-2 evidence.
- **T3 (persistence failure/rollback): CLOSED** per scratch fault-path diagnostic evidence.
- **T4 (three-host admission at final global slot): OPEN.** A planned `tcou` / `hnl-01` / `kah-01` barrier uses three independent detailed background jobs and a 1,295-of-1,296 synthetic start budget. The read-only preflight succeeded, but **no three-host T4 fixture run or concurrent participant execution has occurred**. Plan: [T4 cross-host scratch plan](stage9c-t4-cross-host-scratch-plan.md).
- **T4 recovery/cleanup safeguards implemented:** pure interrupted-ledger validator; read-only foreign-reference checks (including marked events pointing at foreign identities); required operator attestations for *both* normal cleanup and recovery; explicit `--rollback-probe` fault injection inside the cleanup transaction. **These are not yet a live PostgreSQL rollback proof.**
- **T4 evidence tooling implemented:** read-only repeatable-read, five-table full-row SHA-256 fingerprint capture and offline before/after comparison. On `tcou`, invoking as `.venv/bin/python -m scripts.phase5b_stage9c_t4_evidence` succeeded; direct script-path invocation failed with `ModuleNotFoundError` before DB access. The successful preflight produced `/tmp/bf4ps-t4-evidence-preflight.json` with zero rows in `collectors`, `soldiers`, `collection_jobs`, `collection_events`, `stage9c_supervision_runs`, and empty marker event counts. This was **read-only operator evidence**, not a seeded rehearsal.
- **Latest offline validation:** `tcou` checkout `/opt/bf4ps-stage9c-validation`, branch `test/stage9c-admission-concurrency`, commit `8f9c4e9`: syntax exit 0; **35/35 targeted T4 offline tests PASS in 0.51 s**, pytest exit 0. Breakdown: recovery rules 15, cleanup guards 5, evidence comparison 6, CLI safety 9. These are targeted tests, **not a full repository suite rerun**.
- **Scratch identity:** dedicated `bf4ps_scratch_stage9c_integration` on `mak-db-02.bf4statusbot.com` (`192.168.10.78`), role `bf4ps_stage9c_integration`, documented Alembic head `0004_stage9c_supervision_runs`. Keep the original `/opt/bf4-player-stats` checkout untouched. Scratch schema/connection identity must be checked before any writes.
- **Next gates:** (1) finish code/SQL and failure-path review, (2) obtain explicit approval for *single-host scratch fixture writes*, (3) independently capture before/after evidence for a deliberately aborted cleanup transaction and verify exact equality, (4) separately approve actual cleanup/recovery and verify independent zero census, (5) separately approve the three-host T4 admission rehearsal and reconcile host logs, (6) T5 read-only physical-start ledger completeness reconciliation. No approval is implied by passing offline tests or a read-only capture.
- **Operational limits:** no outbound BF4/Battlelog HTTP, no production writes, no migration, no remote host commands, and no activation while these gates remain open.

## Deferred feature roadmap — cross-platform combined profiles (not Stage 9C)

**Status: idea accepted for much later; design only, no implementation or scheduling.** Keep this out of collector reliability, Stage 9C admission, and activation gates.

- **Default identity:** retain each BF4 soldier as a separate platform-specific record keyed by `(persona_id, platform)`. Never merge stored collection, history, weapon, vehicle, or detailed stats across soldiers.
- **Optional fun view:** a user may explicitly choose an unofficial combined profile across verified PC, PS4/PS5-family (schema platform `ps4`), and Xbox-family (schema platform `xboxone`) soldiers. Default views and leaderboards remain per-soldier/per-platform unless separately designed and approved.
- **Automatic associations:** leverage existing `battlelog_profiles` and `profile_soldiers` relationships as possible evidence, but do not assume they prove EA ownership or that every linked platform is discoverable. Verify provenance and confidence from real sources before treating any link as confirmed.
- **Manual linking:** allow a player to request linking an unlinked soldier, **only after a robust ownership/authorization verification process for the target soldier**. Merely knowing a name, persona ID, public Battlelog URL, or shared username is not proof. Do not permit a third party to claim or attach someone else's persona without appropriate verification; if verification is unavailable, leave it unlinked rather than silently accepting a suggestion. The precise proof-of-control method and platform limitations require future research/design.
- **Integrity and abuse controls:** distinguish verified vs user-provided claims; track evidence/provenance, who initiated the link, timestamps, review state, and revocation/unlink history; prevent conflicting claims, impersonation, and arbitrary cross-user linking. Require re-verification or review when appropriate. Do not expose private account identifiers or assume all linked soldiers belong to one person solely from a shared profile.
- **Aggregation semantics:** sum only compatible additive metrics (e.g. kills, deaths, eligible playtime), recalculate derived ratios from totals, show platform breakdown and data freshness, and do not sum ranks, skill, percentages, or non-additive metrics. Label aggregates as unofficial and avoid default combined leaderboards.
- **Future design prerequisites:** verify actual Battlelog/EA linkage behavior and available proof-of-ownership mechanisms, define consent/privacy rules and conflict resolution, document schema changes separately, and design tests before implementation.

**Priority:** explicitly far-future/backlog. This note does not authorize schema migrations, linking endpoints, dashboard work, or a change to Stage 9C **HOLD**.
