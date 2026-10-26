## 2026-10-25 — production ranking resumed with one local replica

- Operator confirmed `hnl-db-01`, `kah-db-01`, and `rnt-db-01` were intentionally stopped because WAN transfer and remote write throughput could not keep up with WAL. They remain offline. Operator authorized changing ranking admission to run with the local `mak-db-01` replica only. The **single-builder** capacity and 32 GiB WAL retention guard remain unchanged.
- On `mak-db-02`, backed up the prior production `public.bf4ps_rank_gate_ready()` function to `/root/bf4ps-rank-gate-before-20261025.sql` (SHA256 `92f35ed98cd7589ba813b0c1e2851cf3dbc23de34bbcb5b38b705413966e0721`). Replaced only the four-slot requirement with `mak_db_01` and changed required count to one. The applied SQL is preserved as `/root/bf4ps-rank-gate-local-replica-20261025.sql` (SHA256 `3cb3ab5cdd376d0815603d571a0a2f0a02da6b2770426f10544ac513ef903cdf`). Equivalent idempotent function source is tracked in `player-collector/deploy/sql/rank_gate_single_local_replica.sql`.
- Re-armed `public.bf4ps_rank_wal_gate` with `target_lsn=pg_current_wal_lsn()`, `primary_started_at=pg_postmaster_start_time()`, and `armed_at=clock_timestamp()`. Immediately after the update, gate remained false until `mak_db_01` replayed the target WAL; subsequently confirmed **gate true**. No gate bypass or forced job claim.
- `mak-01` rank worker immediately logged `claimed vehicle 26 all kills`. Production DB then confirmed **one successful ranking job at 2026-10-25 08:42:50 UTC**, **one active claim**, and gate still true. This establishes actual resumed progress, not just Docker uptime.
- **Rollback:** use the original backed-up function SQL on `mak-db-02` with `runuser -u postgres -- psql -v ON_ERROR_STOP=1 -d bf4_playerstats -f /tmp/<reviewed-backup-copy>.sql`. Reverting to the four-slot gate will intentionally pause builds until the remote replicas return. Do not drop replication slots or weaken WAL safety to speed builds.
- **Operational limitation:** continuous operation is conditional on `mak_db_01` remaining healthy, WAL retention under 32 GiB, and the DB primary remaining current; any safeguard failure pauses ranking. Monitor completed-job timestamps and gate readiness. The website ranking-reader parity test and clean production cutover are separate remaining tasks.

## 2026-10-25 — ranking worker and PostgreSQL HA read-only inspection

- Operator confirmed **single-builder, slow ranking is intentional**; no concurrency or refresh interval changes authorized. Inspection nevertheless found a stalled queue, not merely slow throughput.
- `mak-01` Docker container `bf4ps-distributed-rank-mak01` is running (image `bf4-player-stats:collector-ranking-versions-0016-candidate`), no restarts, with only worker registration in logs. Its admission code checks `public.bf4ps_rank_gate_ready()` and returns no claim if false.
- Production DB (`mak-db-02`) rank queue: **2,624 jobs**, all due, **0 claimed**, latest successful and updated job **2026-10-22 06:31:05 UTC**; capacity is **one active build**, 180-second lease. Rank gate returned **false**.
- Gate requires four named streaming physical replication slots (`mak_db_01`, `rnt_db_01`, `hnl_db_01`, `kah_db_01`), each caught up to its recorded WAL target; the primary currently has **only `mak_db_01`** and one streaming replica. `bf4ps_rank_wal_gate` has a target LSN and armed time from October 22. This is an intentional fail-closed HA/WAL safeguard, not an application error.
- Remote inspection: `hnl-db-01` PostgreSQL 16/main stopped cleanly **2026-10-22 07:56:22 UTC**; `kah-db-01` stopped **07:56:27 UTC**; `rnt-db-01` stopped **2026-10-23 09:59:49 UTC** and its `postgresql@16-main.service` is **masked**. All three have ample free disk. Generic `postgresql.service` showing active is not evidence the actual 16/main cluster is running.
- **No DB services restarted, no masks changed, no replication slots created, no admission gate weakened, no ranking jobs claimed, no production API cutover.** Before restoring HA, confirm the operator's intentional maintenance state and validate replica rebuild/catch-up procedure; then confirm all four slots stream and the rank gate re-arms safely. Only after fresh rank publication can GitHub's newer ranking API be parity-tested and deployed.

# BF4 Player Stats — Current Production Checkpoint

**Reconciled:** 2026-10-25 UTC. **Scope:** production player-collector release; other components require independent source-parity audits.

## Authoritative release and production evidence

- GitHub `main` is the intended source of truth. Player collectors were built from reviewed commit `6589a7ef0ac98707d0088c2ac910aa787d594631` and deployed to nine nodes: `mak-01`, `mak-02`, `mak-03`, `mak-04`, `hnl-01`, `hnl-02`, `hnl-03`, `kah-01`, `rnt-01`.
- Every running collector reported the exact release Git revision label, direct Python import showed `REQUEST_INTERVAL_SECONDS=4.0` and exclusion-aware job claims, the three audited collector/ranking module hashes matched GitHub, restart count was zero and fresh successful collection logs were observed.
- Production database `bf4_playerstats` reported Alembic `0018_distributed_rank_queue` on October 25. Four active player exclusions were counted at that read. No schema migration or change to moderation policy was performed.
- The existing physical dispatch ceiling is 4,800 per rolling hour; the 4-second per-egress interval does not override it. BF4SW request pacing was not changed.
- Eight collector nodes run individually managed Docker containers with their previous stopped container preserved for rollback; `rnt-01` remains managed by its Docker Compose override.
- All images were built from the same Git commit on each host, **not** transported from one immutable registry digest. Their image IDs differ. The build therefore has verified source identity but not byte-for-byte binary reproducibility.
- Container smoke tests and selected pytest checks passed (7 tests, 4 subtests). A full integration suite, sustained post-rollout soak, replica/failover validation and rate-limit safety measurement remain open.

## 2026-10-25 website and platoon reconciliation checkpoint

- **Community Statistics sidequest deployed and committed:** `website/api/community_export.py` and `website/site/community.html` now use the homepage four-resource full-stat completion definition and show `% of indexed` by platform. Commit `d42374f` on `main`; exporter ran successfully and the public site file was updated. The community snapshot counted 199,169 full-stat soldiers at deployment; counts are dynamic.
- **Preserved without overwriting:** `tcou` tracked working-tree differences in `/root/bf4ps-source-audit-20261025/tcou-tracked.patch` (plus status and HEAD manifests); `mak-05` and `hnl-03` tracked diffs and untracked lease/test files in host-local `/root/bf4ps-source-audit-20261025/`. These are temporary operational preservation artifacts, not GitHub commits or complete backups of every untracked website asset.
- **Platoon parity evidence:** SHA-256 matches between `mak-05` and `hnl-03` for `scripts/platoon_shared_lease.py`, `scripts/import_platoon_rosters.py`, `scripts/platoon_queue_worker.py`, and `scripts/admit_platoon_soldiers.py`. Their tracked HEAD revisions and other modified files differ, so full parity remains unverified. No platoon service was restarted or redeployed.
- The `tcou` website checkout's normal remote refspec did not include `origin/main`; it was explicitly fetched for the clean sidequest worktree. Do not reset or overwrite the existing dirty website branch.

## 2026-10-25 UX labels and source parity findings

- Live main page now labels `Soldiers indexed` as **Total # of Soldier Names Recorded** and `Platoons collected` as **Total # of Platoon Names Recorded**. Community Statistics uses the first label, and the live platoon directory displays **N platoon names indexed**. The live homepage and platoon directory JavaScript were committed in `a85c61f`; the live directory JavaScript was previously absent from GitHub `main`.
- **Platoon source parity:** On `mak-05`, eight production modules matched GitHub `main` byte-for-byte, including shared lease, importer, queue worker, admission, discovery, exporter, submit API and alternating scheduler. On `hnl-03`, six checked modules matched, including roster parser and alternating scheduler. This does not certify complete trees or service startup configurations; do not blindly replace active services.
- **Website source parity:** `tcou` admin console and community exporter matched `main` byte-for-byte. The live general leaderboard contains an extra official platoon-tag LATERAL join absent from `main` (potential missing feature). The live leaderboard API has a conservative revision-0017 precompute gate while `main` has newer rank read handling (production revision 0018). The manual request API differs in comments only in the inspected hunk; temporary dashboard export differs in snapshot publication behavior. `homepage_summary_export.py` and the live `platoons.html` were absent from `main` at audit time. Each needs a deliberate reconciliation/test before any website service deployment.
- **Next gate:** reconcile the live platoon tag join and missing homepage summary/export and platoon HTML assets into reviewed GitHub commits; run website regression tests and compare output contracts before restarting the website API. Preserve production runtime files and configuration.

## 2026-10-24 22:22 HST — Discord link-preview regression investigation

- A Discord screenshot showed an older soldier link with personalized `BF4 Player Stats — mauirixxx` title, a personalized platoon preview, and a newer soldier link with generic `BF4 Player Stats — Soldier Dossier` title. Generic text is the PHP fallback when the internal soldier-detail lookup fails or times out; Discord may also cache previously fetched metadata.
- Verified with a Discordbot user agent that both `https://bf4playerstats.com/soldier.html?id=4345649` and the `www` hostname returned personalized `og:title` for `madbiker920`; soldier ID 1 returned `mauirixxx`. Measured internal lookup ~0.84 s. The production PHP lookup timeout was only 2 seconds.
- **Preserved missing live files in GitHub main**: `website/site/share-preview.php`, rewrite rules in `website/site/.htaccess`, and `website/api/share_preview_index.py` (commit `1d91eb6`). This prevents a future GitHub-based deployment from silently removing dynamic soldier/platoon preview metadata.
- Backed up live PHP to `/root/bf4ps-source-audit-20261025/share-preview.php.before-timeout`, increased internal lookup timeout from 2 to 5 seconds, deployed the PHP file without restarting services, verified HTTP response contains player-specific `og:title`, and committed the same one-line change in `23dc025`.
- Remaining reliability consideration: avoid caching a generic fallback as a permanent Discord preview when backend lookup temporarily fails. A static periodically refreshed soldier metadata index or a short-lived 503 response for transient lookup failure could be designed separately, without exposing private data.

## 2026-10-24 22:15 HST — production read-only rank eligibility check

- Ran `/tmp/bf4ps-rank-readonly-check.py` on `tcou` with the production website database credentials, a `REPEATABLE READ` transaction, `SET TRANSACTION READ ONLY`, and a 7-second local statement timeout. Confirmed database `bf4_playerstats`, Alembic `0018_distributed_rank_queue`.
- Production has **414** entries in `equipment_rank_published`. Latest corresponding generation completed **2026-10-22 06:30:46 UTC**, oldest **2026-10-21 08:00:10 UTC**; **zero** published generations were within the rank reader's **3-hour freshness window** at inspection.
- Called GitHub main's `rank_read_path_hourly.get_precomputed_page()` on six sample `all`-platform vehicle-kills scopes (item IDs 10, 20, 27, 37, 41, 45). All returned `None` (correct fail-closed fallback behavior). **Precomputed-versus-live rank parity is not established** because no fresh eligible generation exists. No DB writes or production service restarts.
- **Release gate remains open:** investigate why ranking publications stopped and restore fresh rank generation safely; then compare rank results and API contracts on fresh scopes, including search/divisions/pagination and canonical vehicle families, before changing production API. Do not silently enable a stale rank reader.
- Single summary publisher safeguard fixed in commits `6dc26c9` and `a269e50`; regression contract added in `6d177df`. The clean-checkout `unittest` suite now passes **51 tests**.

## 2026-10-24 22:06 HST — exporter ownership and ranking cutover audit

- **Confirmed active owner of `homepage-summary.json`:** `bf4ps-homepage-summary.timer` invokes `bf4ps-homepage-summary.service`, running `/opt/bf4ps-website/api/homepage_summary_export.py`; last observed execution completed successfully at 22:06:30 HST. This script writes the JSON atomically with `os.replace`. The independent `bf4ps-community-export.timer` writes `community-stats.json`, not the homepage summary.
- The **currently deployed** `/opt/bf4ps-website/api/temp_dashboard_export.py` writes only `temp-stats-data.json` and does not write `homepage-summary.json`, although it contains an unused `SUMMARY_OUT` constant and `homepage_summary()` helper. **GitHub main's version differs and includes summary publication**. Preserve single-writer ownership: do not activate that GitHub summary publication concurrently with the homepage-summary timer. Recommend removing duplicate publication from the dashboard exporter in a dedicated source change, retaining the dedicated timer as owner.
- **Equipment rank API cutover:** GitHub main opts into `rank_read_path_hourly.get_precomputed_page()` when `BF4PS_PRECOMPUTED_RANK_READS=1`, with canonical vehicle family IDs and fallback on missing/stale generation. Live `tcou` has an obsolete exact revision check for `0017_rank_immutable_scores`, so at the production `0018_distributed_rank_queue` revision it skips the precomputed reader. This is a **real behavioral difference** and requires a read-only parity test of published generations, ranks, pagination, search, and divisions before replacing the live service. The rank reader's own docstring requires a `REPEATABLE READ, READ ONLY` transaction. No production leaderboard API restart has been performed during this audit.
- The `bf4ps-leaderboard-api` and `bf4ps-manual-api` services were active during the audit. The manual API is not part of the remaining source delta except a misleading comment in the live checkout.

## 2026-10-24 website clean-checkout regression milestone

- `main` now contains the production homepage summary exporter, live platoons HTML/JS, general leaderboard platoon-tag join, artwork storage module, and fifteen Python regression test modules (commits `5d26641`, `2d74864`, `3999a6a`). The live UX labels were committed earlier in `a85c61f`.
- **Verified:** using the existing `tcou` website virtual environment, `cd website && PYTHONPATH=. /opt/bf4ps-website/.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -q` returned **48 tests, OK** on the clean GitHub worktree. No pytest dependency is required for this suite. Updated three stale test contracts and restored missing artwork and staging dependencies.
- **Manual API:** GitHub `main` and running `tcou` manual request API match functionally; only a comment differs. Existing service binds loopback and the private LAN address, uses a fixed client allowlist, private token, origin check, and rate limiting. Both `bf4ps-manual-api` and `bf4ps-leaderboard-api` were active at verification. Do not replace this API with an older localhost-only version.
- **Equipment ranking API:** running `tcou` code has a restrictive legacy Alembic-0017 gate; GitHub `main` has newer opt-in hourly rank reader and canonical vehicle family handling. `BF4PS_PRECOMPUTED_RANK_READS=1` in the production environment. Production DB is revision 0018 per previous schema audit. Treat GitHub as intended newer source, but **do not deploy until a read-only production parity/smoke test validates the newer reader**.
- **Dashboard exporter:** `main` includes atomic compact homepage-summary publication missing from the older local `temp_dashboard_export.py`; independent `homepage_summary_export.py` is already running in production. Confirm publication ownership/timers before cutover to prevent concurrent writers.
- **Not yet a completed release:** no production API swap, end-to-end live DB query comparison, cross-host runtime manifest, or rollback rehearsal has been performed. Preserve the dirty production checkout and excluded artwork deletions.

## Remaining repository source-parity work

- The collector's deployed `/app/bf4ps` modules were compared with GitHub `main` on `mak-01`: all matched except `distributed_rank_queue.py`, for which GitHub contains a newer replication guard and priority behavior. The rebuilt GitHub image retains that newer version.
- **Not yet established:** complete GitHub/deployed parity for the website/API (`tcou`), Discord bot, platoon collectors (`mak-05`, `hnl-03`), discovery service and ranking-worker services. Do not call the entire multi-component project standardized until those audits and their release rollouts pass.
- **Additional service inventory (2026-10-25):** `tcou` website checkout is `perf/weapon-top50-live-20261019` (`c0f61af`) and runs admin, discovery, leaderboard, manual and platoon submission services; `mak-05` platoon checkout is `feature/platoon-design-20261018` (`8be3fad`), while `hnl-03` is on that branch at `378deec`; Discord HA containers on `mak-01`/`rnt-01` use `bf4ps-discord:card-v28`; `mak-01` ranking worker and weapon sync use `bf4-player-stats:collector-ranking-versions-0016-candidate`. These are **not** verified against GitHub `main` or included in the nine-node collector release. Preserve them until their own code-parity and safe cutover reviews.
- Publish one immutable image digest to a trusted registry (or distribute a single verified image archive), then deploy by digest; stop relying on independent per-node builds for byte-identical release verification.

See [production collector release procedure](../player-collector/deploy/docker/PRODUCTION-RELEASE.md), [collector architecture](collector-architecture.md), [path to completion](path-to-completion.md), and [operational schema](operational-schema.md).

---

## Historical Stage 9C checkpoint (2026-10-10)

The material below is preserved as historical evidence, **not** the current production state.

# BF4 Player Stats — Current State

**Last reconciled:** 2026-10-10
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


### T4 cleanup cascade safety — 2026-10-09 (implementation pending operator validation)

- The documented schema and initial migration identify eight soldier-dependent tables with cascading foreign keys: `soldier_sources`, `soldier_names`, `profile_soldiers`, `detailed_stats_current`, `detailed_stats_history`, `soldier_weapon_stats`, `soldier_vehicle_stats`, and `collection_state`.
- T4 cleanup/recovery now queries each for fixture-soldier references and refuses deletion if any are present. This prevents silent deletion of unexpected dependent rows. Eight new offline rejection cases were added.
- **Code pushed, not yet operator-tested**; the previous 35/35 result predates these changes. Next checkpoint: compile and run the targeted 43-test suite. No scratch writes or T4 rollback rehearsal approved. Production HOLD.

### T4 fixture identity review — 2026-10-09 (operator test pending)

- Operator confirmed the prior cascade safety patch at commit `380911b`: **43/43 targeted offline tests PASS**, syntax exit 0, pytest exit 0, on `tcou`.
- New read-only pre-delete checks now refuse job-to-soldier identity drift (expected synthetic name, PC platform, detailed/background/active job), fixture collector name/hostname/lane/egress drift, and foreign collector `current_job_id` references to fixture jobs.
- Three new fake-connection rejection tests added. **Changes pushed but not yet operator validated**; expected targeted total is **46 tests**. No scratch fixture writes authorized; PostgreSQL rollback probe and three-host execution remain untested. Stage 9C production HOLD.

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


## T4 operator checkpoint and inspector correction candidate — 2026-10-10

**Supersedes earlier unexecuted T4 descriptions.** Three-host scratch run `709bc574-6ebf-4f05-adc9-e0fa3ae620a2` yielded one WIN (`hnl-01` job 46), two DENIED (`tcou` job 45; `kah-01` job 47), full 3 READY / 1 RELEASE / 3 DONE ledger, zero BF4 HTTP, all processes stopped, preserved read-only JSON, guarded cleanup PASS and independent five-table zero census PASS. The inspector returned 1295 rather than its unconditional 1296 expectation; `_usage()` excludes expired unstarted leases, and the winner lease expired at 06:21:31 UTC. Exact inspection time unrecorded; hypothesis not proven. See [T4 execution record](stage9c-t4-three-host-execution-and-inspector-investigation.md).

**Current engineering branch:** `fix/stage9c-t4-inspector-lease-expiry` adds a time-aware scratch inspector assertion and offline regression cases. These changes are **authored, not yet operator-tested**. T4 formal closure OPEN, T5 and O1–O4 OPEN, Stage 9C production HOLD / NOT AUTHORIZED.

## 2026-10-25 — catalog bloat and leaderboard name colors
- The live homepage now colors soldier names by platform: PC orange, PlayStation blue, Xbox green, matching BF4SW dashboard platform palette; the highlighted-soldier color retains precedence.
- Soldier dossier 1161043136 returned 503 after the 5-second SQL statement timeout. `EXPLAIN (ANALYZE, BUFFERS)` showed 6.748 seconds for the top-15 weapons query, with ~587k shared buffer reads largely from `weapon_catalog` index lookups.
- Production `weapon_catalog` had 174 live rows, ~1.12 million estimated dead rows, and 212 MB heap; `vehicle_catalog` had 82 live rows, ~526k dead rows, 108 MB heap. Repeated `ON CONFLICT DO UPDATE` of unchanged catalog metadata, including `last_seen_at`, is the identified churn source.
- Source patch in `player-collector/bf4ps/{weapon,vehicle}_persistence.py` reads existing catalog metadata and reuses the ID without UPDATE when identical; changed/new metadata still takes the existing upsert path. This code requires collector test verification and a coordinated fleet image rollout; editing GitHub alone does not fix running containers.
- **Important cleanup blocker:** `mak-db-02` has an idle-in-transaction backend PID 1514626, client 192.168.10.71, transaction age ~14h39m, with a pinned `backend_xmin`. Identify and safely close that transaction before expecting VACUUM to reclaim dead versions. No backend was terminated and no VACUUM FULL attempted.

### 2026-10-25 catalog cleanup execution and source recovery
- Identified the long-lived idle transaction PID 1514626 (`192.168.10.71`, migrator account, approximately 14h42m old, `SELECT pg_try_advisory_lock($1)`), terminated **only that backend** with `pg_terminate_backend`; no service stopped.
- Completed ordinary online `VACUUM (ANALYZE)` for `weapon_catalog` and `vehicle_catalog`. Estimated dead tuples fell to ~5,818 weapons and ~2,247 vehicles; heap sizes fell from 212 to 149 MB and from 108 to 76 MB, respectively. No VACUUM FULL or table lock/rewrite.
- The previously failing soldier dossier (`soldier_id=1161043136`) returned HTTP **200 in 45 ms** from the loopback API immediately after cleanup (previously 503 after 5 seconds).
- Discovered `/opt/bf4ps-production` on `mak-01` already contains a **better, earlier optimized catalog reconciliation implementation** (commit `bfc02c3`): bulk lookup of existing GUIDs, 15-minute bounded `last_seen_at` refresh, recheck under advisory lock only when metadata changes/refresh is due, and bulk inserts. The running Docker image `bf4-player-stats:git-6589a7e` does **not** contain this code; do not confuse host source with deployed image.
- Recovered the optimized modules `bf4ps/{weapon_persistence,vehicle_persistence,catalog_refresh,bulk_values}.py` and their four test modules from the old commit via recovery branch `recovery/catalog-optimized-20261025`, superseding the initial per-row read patch. On `mak-01` the optimized source passed **21 focused pytest tests** in a temporary disposable container. The optimized source must still be built and deployed consistently across collector nodes; do not deploy a generic GitHub image over a dirty host tree without validating feature parity and existing service settings.

### 2026-10-25 — nine-node production collector rollout
- Built minimal Docker overlays `bf4-player-stats:catalog-fix-3900d15` on top of each node's existing `bf4-player-stats:git-6589a7e`, copying only the four catalog-related Python modules from GitHub commit `3900d15`. Reproducible overlay Dockerfile: `player-collector/deploy/docker/Dockerfile.catalog-hotfix` (build context `player-collector`). Four file SHA256s: weapon `994b0edc612f845e07aa8801c5dba886bd8287a4351a0efc77f9914ba5123b1f`, vehicle `a7faf230146c63909f79578aa9058fd883c8ab3c383241a72f37a00a100dffac`, refresh `ddd55025d357a57112e5be294bf8455dda29c3b17b019ed08d5049d72a00bed0`, bulk `91e0ce51bf09726dfafd729c0f40913a74b0f267556c098c82ec416e22d14249`.
- Pilot `mak-02` succeeded with live weapon, vehicle, detailed, and profile jobs. Then rolled out to `mak-01`, `hnl-01`, `kah-01`, `mak-03`, `mak-04`, `hnl-02`, `hnl-03`, and `rnt-01`. Verified all **nine** containers running the new tag and successful post-restart collection logs. No database schema change and no change to per-egress pacing or request budget.
- On eight individually managed nodes, original Docker containers were stopped and renamed `bf4ps-production-collector-before-catalog-20261025` for rollback. The original runtime environment was saved root-only as `/root/bf4ps-collector-env-backup-20261025` on each host; never commit or print these secrets. Original image `bf4-player-stats:git-6589a7e` retained. To roll back: stop/remove new container, rename old one back, and start it (checking the node's configuration and leases first).
- On `rnt-01`, collector is managed by Docker Compose (`docker-collector-1`), not the standalone container name. Backed up `/opt/bf4ps-ranking-0016-deploy/override.yaml` to `override.before-catalog-20261025.yaml`, changed only the collector image tag, and ran `docker compose -f compose.yaml -f /opt/bf4ps-ranking-0016-deploy/override.yaml --profile collector up -d --no-deps --no-build collector`. Rollback by restoring that override and recreating only the collector. No other Compose services changed.
- After rollout, dossier `1161043136` still returns HTTP **200 in 37 ms**, and the ranking admission gate is still **true**. Repeated ordinary `VACUUM (ANALYZE)` on both catalogs. PostgreSQL dead-tuple statistics may lag or reflect concurrent transactions; monitor `n_tup_upd`, dead-tuple trends and actual dossier latency before claiming catalog bloat is permanently eliminated. No `VACUUM FULL` performed.

### 2026-10-25 — second catalog hotfix, metadata oscillation
- After first rollout, `pg_stat_user_tables.n_tup_upd` continued rising rapidly (for example weapon catalog 1,976,571 at 17:41 UTC to 1,989,227 at 17:46 UTC). The original `needs_refresh` refreshed immediately whenever a descriptive name/slug/category differed. Cross-platform metadata differences can therefore defeat the 15-minute sighting throttle. This remained a **measured concern**, not proof of which worker wrote each row.
- Updated `bf4ps/catalog_refresh.py` in commit `7e94f8e` to throttle **all** catalog rewrites, including metadata differences, to at most once per item per 15 minutes through that code path; added tests for deferred metadata changes and stale metadata refresh. This trades immediate descriptive metadata changes for bounded write amplification and stable catalog IDs.
- Built second overlay `bf4-player-stats:catalog-fix-7e94f8e` on top of `catalog-fix-3900d15`, replacing only `catalog_refresh.py`. Verified the new throttle in disposable container imports on all nine nodes, then restarted each collector with preserved settings. Verified all nine on new image and each logging successful collection activity. The prior catalog-v1 containers on standalone hosts are retained as `bf4ps-production-collector-catalog-v1-20261025`; pre-catalog original containers are also retained.
- RNT Compose override now selects `bf4-player-stats:catalog-fix-7e94f8e` (original override backed up). No change to ranking builder or platoon collectors.
- **Open monitoring:** `n_tup_upd` was still increasing during/shortly after the second rollout. It is not yet verified that all catalog churn has ceased; continue measuring update-rate deltas after stabilization and investigate other writers if the rate remains above the expected few hundred catalog updates per 15-minute period. Do not claim permanent resolution solely from successful collector starts.


### 2026-10-25 — actual collector import-path root cause

The previous nine-node image hotfix did not change the installed `site-packages/bf4ps` package imported by `/app/scripts/bf4ps_production_collector.py`. Database evidence identified old single-row catalog upserts still executing. Corrected the installed package inside all nine running containers and restarted them; all nine subsequently verified importing optimized persistence. Built reproducible corrected image `bf4-player-stats:catalog-fix-installed-20261025` on all nodes. **Existing containers still use the old image tag**, so explicitly switch their image configuration on future recreation. Both catalogs were vacuumed online, and concurrent index maintenance began. See [CATALOG-IMPORT-PATH-RECOVERY-20261025.md](CATALOG-IMPORT-PATH-RECOVERY-20261025.md).


#### Catalog maintenance completion

All nine running collector containers verified the optimized imported persistence code. Both catalogs vacuumed; all four catalog indexes concurrently reindexed successfully after releasing one stale idle transaction. Post-maintenance `n_dead_tup=0` for both; catalog index sizes total 80 kB. Corrected images were built on all nine nodes, but running container image references have not yet been changed. Continue monitoring catalog update rates and use corrected image tag on recreation.


### 2026-10-25 — corrected collector images deployed fleet-wide

Completed image-reference cutover for all nine soldier collectors to `bf4-player-stats:catalog-fix-installed-20261025`. All nine verified running with successful collection logs and zero restart counts. Eight standalone nodes retain previous containers for rollback; RNT's Compose override was updated with a backup. Post-cutover PostgreSQL counters showed no further catalog updates since the maintenance baseline and zero dead tuples at that check. This supersedes the earlier warning that the corrected image was only built, not selected. See `docs/CATALOG-IMPORT-PATH-RECOVERY-20261025.md`.

### 2026-10-25 — management next-ten queue display

The admin `queue/players` endpoint now filters actively excluded soldiers using the same `(platform, persona_id, active)` exclusion rule as the collector claim path, and orders pending priorities as `interactive > active > recent > bootstrap`, matching the worker priority-class mapping. Running jobs still appear first. This is a read-only presentation correction; no queued jobs were modified or deleted. A 2026-10-25 inspection found approximately 979k eligible pending jobs, including one old excluded profile job (`U_M320_FLASH`, `data_integrity_anomaly`) incorrectly shown in the admin dialog. Other older profile jobs were observed moving into running state, so an old eligibility date is not by itself evidence of a stuck job. The displayed list is approximate because workers claim concurrently and resource/lane gates also affect actual admission.

### 2026-10-26 — admin Collection Overview 502 permission fix

The admin Collection Overview SQL (introduced during the platoon JSON-to-API cutover) joined `platoon_roster_accounts`, `platoon_roster_personas`, and `detailed_stats_current`, but the production `bf4ps_admin_moderation` database role lacked SELECT permission on all three tables. The handler raised `psycopg.errors.InsufficientPrivilege`, and Apache surfaced the broken response as HTTP 502. On primary `mak-db-02`, granted **SELECT only** on precisely these three public tables to `bf4ps_admin_moderation`; no write privileges or schema changes. Verified the **full original overview query** as `SET ROLE bf4ps_admin_moderation` under its 12-second statement timeout; returned 11,035 platoons, 280,147 visible roster accounts, 275,463 unique supported soldiers, and 34,456 unique tracked soldiers. The endpoint requires authenticated admin access, so the final browser response was not independently exercised. Maintain these grants in future role provisioning.

### 2026-10-26 — watchdog design requested

Operator requested BF4SW-style Discord notifications to multiple BF4PS infrastructure administrators for node, service, database, and disk failures. Design and prerequisites are in `docs/INFRASTRUCTURE-WATCHDOG-DESIGN.md`. This feature is **not yet deployed** and cannot send notifications until a private Discord destination and administrator enrollment policy are configured. Existing bounded ranking GC and disk-recovery changes are recorded in `docs/DISTRIBUTED-RANKING-WORKERS-DESIGN.md`.
