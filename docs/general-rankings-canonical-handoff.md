# BF4PS GENERAL LEADERBOARD SNAPSHOTS — CANONICAL HANDOFF / SOURCE OF TRUTH
Last evidence review: 2026-11-16. Repository: mauirixxx/BF4-Player-Stats, branch main.
Purpose: make a new conversation able to resume without inventing schema, rerunning completed work, or accidentally activating an unfinished production feature.

> READ THIS FIRST. This is an evidence-backed handoff, NOT a claim that production is upgraded.
> The source code and current database schema/migrations are authoritative over this narrative.
> Before any schema-dependent implementation or SQL, read docs/database-schema-reference.md AND the CURRENT Alembic migrations. If they disagree, reconcile before work. Update schema reference in the same change set as any schema change.

## 0. Fast orientation: what is done, what is not

DONE AND IN GITHUB:
- Additive Alembic migration 0026 for precomputed general ranking generations, rows and publication pointers; schema reference updated with proposed schema.
- Independent opt-in writer in player-collector/bf4ps/general_rank_publisher.py, one explicit metric/platform invocation, atomic publication transaction, advisory transaction lock and strict Alembic 0026 guard.
- Independent opt-in ranking reader in player-collector/bf4ps/general_rank_reader.py; optimized indexed name/alias search; as-of rank semantics, dynamic exclusions, deleted-identity suppression and metadata.
- Website reader copy in website/api/general_rank_snapshot.py, deliberately decoupled from player-collector Python packaging.
- Feature-flagged website API route in website/api/leaderboard_api.py. Flag BF4PS_GENERAL_RANK_SNAPSHOT_READS=1; disabled by default. Legacy fallback when no published generation; feature flag off uses legacy. The production database-name guard is intact.
- Docs: docs/general-rankings-precompute-plan.md, docs/general-rankings-freshness-decision.md, docs/general-rankings-website-rollout.md.
- Tests: player-collector/tests/test_general_rank_publisher.py, player-collector/tests/test_general_rank_reader_contract.py, player-collector/tests/scratch_general_rank_retention_race.py, website/tests/scratch_general_rank_http_smoke.py; existing website tests.
- Isolated scratch HTTP smoke passed snapshot first page, name search, and flag-off legacy path. Selected tests 16/16 passed at last run.

NOT DONE / DO NOT ASSUME:
- Migration 0026 NOT deployed to production as of last verified status. Production head recorded as 0025; independently verify before any rollout.
- NO production general publisher, general ranking scheduler, retention service or fleet-wide activation. NO feature flag enabled in production.
- NO production-sized *measured writer benchmark* with WAL, disk, replica replay lag, transaction duration and repeat-cycle footprint. A benchmark harness was drafted at /tmp/bf4ps_publish_benchmark.py on RNT-01, but its execution was blocked by a tool safety check; do NOT report any results from it.
- NO 56-scope exhaustive parity certification, no successful HTTP missing-pointer fallback test, no HTTP exclusion-after-publication test, no live production canary.
- NO settled retention cadence, production storage budget, scheduler sharding/fencing design, freshness SLA or fallback retirement decision.
- The website's snapshot UI label may not yet be visible to users; response metadata exists but frontend display must be verified.
- The reader flag must NEVER be enabled against production schema 0025: missing tables could cause 503 rather than fallback. Rollout order matters.
- The single publisher uses a GLOBAL advisory lock, intentionally serializing all metric/platform scopes. Do not claim it is distributed/sharded or ready for all fleet nodes.
- The standalone publisher currently runs one scope only; there is no scheduler or production operational supervision.

## 1. User-approved product contract — DO NOT REDESIGN

This project ranks Battlefield 4 players across the COMPLETE eligible population, not only a Top 50 or Top 500. The user explicitly chose continuously refreshed periodic AS-OF snapshots, rather than per-request full-cohort live ranking. A 24/7 publication cycle is acceptable, but refresh frequency must be measured and established, not invented.

General metrics (14):
kills, total_score, wins, time_played_seconds, conquest_score, rush_score,
team_deathmatch_score, domination_score, obliteration_score, defuse_score,
capture_the_flag_score, air_superiority_score, carrier_assault_score, chain_link_score.

Platforms (4): all, pc, ps4, xboxone. Total 56 scopes.

Global rank calculation happens BEFORE name search, division filter or pagination.
Ties: SQL rank() over value descending. Deterministic position:
row_number() over (value DESC, soldier_id).
Division cuts (top percentages): 3, 8, 15, 25, 35, 50, 65, 80, 90; 10 divisions.
The response retains population, filtered_count, page, page_size, total_pages,
metric, rows, rank, position, value, top_pct, division, hours_source_seconds,
soldier_id, current_name, persona_id, platform, country/flag and platoon data.
Snapshot metadata includes published_at, generation_id; website adds
rank_updated_at and rank_source=published_snapshot. Legacy adds rank_source=live.

A snapshot's position, rank, division and population remain frozen until the
next successful publication. New soldiers, newly eligible soldiers and stat
changes DO NOT invalidate a snapshot. Current names, aliases, profile metadata
and platoon display are joined at read time. Currently excluded players and
deleted identities MUST disappear immediately from snapshot results, WITHOUT
renumbering survivors; gaps are expected and filtered_count can differ from
population. The website must clearly communicate AS-OF publication time.

## 2. Database schema: read migrations before touching SQL

Read docs/database-schema-reference.md and
player-collector/migrations/versions/0026_general_rank_snapshots.py.
Current schema reference labels 0026 PROPOSED / NOT DEPLOYED and production
Alembic head 0025_compact_lookup_fk_idx (verified on MAK-DB-02 and replicas
MAK-DB-01/HNL-DB-01/RNT-DB-01 on 2026-11-06; KAH-DB-01 unverified).

0026 adds:
- general_rank_generations: generation_id bigint identity PK; metric text;
  platform text; population bigint; created_at timestamptz; completed_at
  timestamptz nullable.
- general_rank_rows: PK (generation_id,position); generation_id FK CASCADE;
  soldier_id bigint (NO FK to mutable soldiers); value bigint; rank bigint;
  division smallint; hours_source_seconds bigint nullable;
  unique (generation_id,soldier_id);
  index (generation_id,division,position).
- general_rank_published: PK (metric,platform), generation_id FK to
  generations, published_at timestamptz.

Publisher source joins soldiers, collection_state, detailed_stats_current,
player_exclusions; reader joins soldiers, soldier_names, player_exclusions,
profile_soldiers, battlelog_profiles, platoon_soldier_discovery, platoons.
Platoon-related tables are managed separately from the core Alembic migrations;
the isolated scratch test database contains compatibility tables.
Migration 0019_soldier_search_trigrams.py supplies lower(current_name) and
lower(name) pg_trgm GIN indexes. Do not guess any further column/table shape.
Do not use production MAK-DB-02 for unrelated compute-heavy scratch work.

## 3. Source paths and call graph

Writer:
player-collector/bf4ps/general_rank_publisher.py
- build_scope(conn,metric,platform) validates allowlists before DB access.
- pg_advisory_xact_lock(640041,260026) serializes all scope builds.
- exact Alembic 0026 guard.
- one transaction inserts generation, INSERT SELECT with window functions,
  updates population/completed_at, atomically upserts published pointer.
- --execute explicitly required; no implicit writes on import or startup.
- Caller owns transaction and commit. A failure rolls back all.
- No scheduling or retention included.

Reader:
player-collector/bf4ps/general_rank_reader.py
- query_page(conn,metric,platform,page=1,page_size=50,search='',division=0)
- Validates metric/platform/page/page_size/division/search length.
- Looks up published pointer + completed generation; None means no snapshot.
- Count and bounded page use same generation; current exclusions/deletions
  filtered. Search resolves soldier_id candidates with UNION from current
  names, historical soldier_names aliases and persona_id substring; joins
  snapshot rows AFTER candidate resolution.
- Enriches only selected page with lateral profile/platoon lookups.
- Caller MUST provide a read-only REPEATABLE READ transaction begun before
  first statement for consistent pointer/count/page MVCC.

Website:
website/api/general_rank_snapshot.py — equivalent standalone website reader.
website/api/leaderboard_api.py — /general-leaderboard endpoint, strict DB name
check bf4_playerstats, 5-second statement timeout, environment feature flag,
REPEATABLE READ in snapshot mode, legacy fallback if None. Snapshot mode
bypasses 300-second first-page cache so moderation exclusions are not stale.
Flag off retains existing READ COMMITTED and legacy cache behavior.
website/api/general_leaderboard.py — original live reader; keep intact until
production parity and rollout succeed.
website/site/homepage-paginated.js — experimental lightweight adapter;
its header currently says feature branch/not loaded in production; verify
actual live homepage rendering rather than assuming it is wired.

## 4. Scratch environment and access

RNT-01 remote Desktop Commander device:
aa6d9aec-0414-4ad7-b824-1d53cc1368b2
Repository: /opt/bf4ps-general-rank-scratch
Virtualenv: /opt/bf4ps-general-rank-scratch-venv
Isolated PostgreSQL 16 cluster bf4psscratch on port 5542,
database bf4ps_rank_scratch, Unix socket /var/run/postgresql.
Connection URL (nonsecret local peer auth):
postgresql+psycopg://postgres@/bf4ps_rank_scratch?host=/var/run/postgresql&port=5542
Run scratch database tests under local postgres OS account. NEVER aim scratch
harnesses at production. The original 16/main port 5432 was left down and
unmodified during scratch work. Disk last observed 155G total, 45G used,
104G available (RNT-01 filesystem; not production storage).

Scratch data: approximately 560,000 synthetic source soldiers. Published
kills/all generation 4 with 560,000 rows. Synthetic current names include
scratch_1..1000 and bench_1..559000. Scratch previously contained old
generations 1/2 and small generation 3; confirm current state before use.
A prior measurement reported ~1.681m ranking rows / ~315 MB total ranking
storage at that point. These are scratch measurements, not production facts.

A retention test created and deleted temporary generations 6 and 7, then
restored publication pointer to generation 4; final verification showed
generation 4 published and zero generations 6/7 remaining.
Scratch-only tests are NOT production safety guarantees.

## 5. Evidence and measured performance

At ~560k eligible synthetic soldiers, comparisons with the legacy reader:
Case                         legacy sec    optimized snapshot sec
Default first page             1.692            0.248
Page 100                      1.683            0.253
Division 1                    2.464            0.059
Name search bench_999         2.192            0.123
Very deep page 99999          2.748            0.673

These are observed single-run values, not statistically robust latency
distributions. Earlier snapshot name search ~1.48 seconds; indexed candidate
search ~0.123 seconds (~12x improvement). For five benchmark cases,
legacy payloads matched snapshot payloads after excluding intentionally new
published_at and generation_id fields. The full reader may differ in as-of
semantics when source data changes after publication.

Scratch publication/retention MVCC experiment:
- Open read-only REPEATABLE READ reader and observe generation.
- Another transaction changes published pointer and COMMITs deletion of the
  old generation (including a temporary generation with an actual row).
- Original reader still observes its previous pointer and row using MVCC.
- Pointer and temporary generation restored/cleaned.
- This is a focused race test, NOT proof that aggressive VACUUM/retention,
  sustained load or all long-running readers are safe.

HTTP smoke (2026-11-16): real localhost ThreadingHTTPServer on RNT-01 using
the website handler compiled with ONLY the database-name guard substituted
in memory to bf4ps_rank_scratch; production source guard untouched.
- Flag on: kills/all snapshot generation 4, population 560000, 10 rows.
- Flag on indexed search bench_999: filtered_count 111.
- Flag off: live reader returns 10 rows, population equal to snapshot.
- Missing publication pointer fallback was NOT exercised.
- Selected combined offline regression suite: 16/16 passed.
- The smoke test is stored in website/tests/scratch_general_rank_http_smoke.py.
- The test does not establish production HTTP performance or availability.

## 6. Production context and capacity risk

Production primary MAK-DB-02, PostgreSQL 16; streaming replicas MAK-DB-01,
HNL-DB-01, KAH-DB-01, RNT-DB-01. Replica and primary health MUST be
reverified before any production work. Compact equipment ranking publishers
MAK-01..04 and retention on MAK-01 are separate and must remain unaffected.

Schema reference records MAK-DB-02 2026-11-12 ~346 GB database,
~299 GB equipment_rank_compact_blocks (~297 GB TOAST),
~12.85m dead compact block tuples versus ~2.15m live, ~178 GiB available.
These figures are historical and likely stale. Do NOT extrapolate production
capacity or WAL from scratch ranking size. Compact retention/autovacuum
activity can overlap general publication and distort timings. Monitor current
disk, WAL, replicas, retention, checkpoints, lock waits, CPU and active jobs.
Avoid unplanned VACUUM FULL or rewrite of large compact tables.

A prior live general leaderboard cold request reportedly took ~6.50 sec
before this precompute project. Production is currently using the legacy
general reader unless independently verified otherwise.

## 7. Remaining blockers and exact next steps

1. **Measured full-scope writer benchmark on scratch**: measure a complete
   build_scope on ~560k soldiers with elapsed time, actual inserted count,
   relation size growth and WAL LSN delta; validate committed pointer and
   row count. Record host, PostgreSQL version, timestamp, disk and load.
   The intended scratch harness is /tmp/bf4ps_publish_benchmark.py on RNT-01,
   but its execution was BLOCKED by a tool safety check on 2026-11-16.
   No results exist. Do not bypass safety controls or fabricate metrics.
2. **Scope parity**: compare 14 metrics x 4 platforms (56 scopes) with legacy
   semantics, ties, empty scopes, rank division boundaries, alias/current
   names, persona substring, page boundaries, deleted identities, exclusions,
   metadata. Use scratch fixture and current migration reference.
3. **HTTP fallback**: test flag ON but no published pointer (legacy result),
   flag OFF, and flag ON with published pointer; test 400 invalid inputs,
   503 on real DB faults, 5s timeout, cache isolation, concurrent publication,
   excluded player immediately absent. Use isolated scratch only.
4. **Retention design**: keep current published generation, define grace
   and cleanup pacing, avoid starving readers and avoid storage/WAL growth;
   test repeated full generations and read/cleanup races. No production
   retention service exists yet.
5. **Scheduler**: explicit controlled activation, one-node canary,
   instrumentation, no accidental startup on collectors; evaluate whether
   global lock permits desired 56-scope refresh cadence. Do not copy
   equipment compact scheduler assumptions blindly.
6. **Production prerequisites**: verify Alembic head, permissions, primary
   and every replica, storage and WAL headroom; obtain/record a rollout
   plan and rollback. Apply additive 0026 only after checks and ensure
   collector revision guards don't reject 0026. Never activate website
   snapshot reads against 0025.
7. **Canary**: publish ONE scope on designated authorized writer,
   observe full WAL/replication lag, locks, elapsed time, growth and
   current compact ranking health. Verify publication and read parity,
   then enable feature flag on website with quick rollback path.
8. **Fleet**: expand deliberately after observed safe cadence and
   operational monitoring. Retain live fallback until stable.
9. **Frontend**: show publication timestamp/as-of semantics visibly.
10. **Documentation**: update this handoff with each completed gate and
    actual production observations; reconcile older docs with current
    implementation (some contain outdated TODOs).

## 8. Test commands and boundaries

Offline selected suite from repository root:
  /opt/bf4ps-general-rank-scratch-venv/bin/python -m pytest -q \
    website/tests/test_general_leaderboard.py \
    website/tests/test_homepage_api_metric_compat.py \
    website/tests/test_rank_reader_contract.py \
    player-collector/tests/test_general_rank_publisher.py \
    player-collector/tests/test_general_rank_reader_contract.py

Scratch HTTP smoke requires env BF4PS_DATABASE_URL pointing ONLY to
bf4ps_rank_scratch, PYTHONPATH to website/api and execution under local
postgres user; inspect the harness before running.
Scratch retention harness requires PYTHONPATH to player-collector and the
same isolated DB URL. It MUTATES scratch publication pointers and deletes
temporary generations; inspect and ensure no concurrent benchmark before
running. Never run these harnesses against production.

Publisher CLI requires --metric, --platform and --execute, and writes a
generation; only use on an approved scratch/canary target after schema
verification and safety review. Never treat it as a harmless dry run.

## 9. GitHub provenance and remote access lessons

GitHub: https://github.com/mauirixxx/BF4-Player-Stats
Latest verified commit before this handoff: be3a0e7 (2026-11-16).
The RNT-01 HTTPS Git remote lacked credentials; direct git push failed.
Use the connected GitHub integration to create/update files, then fetch
origin/main and align the RNT-01 checkout after verifying content.
Historical duplicate-content commits had diverged; local backup branches
were preserved before alignment. Do not force push or erase history.
Useful historical commit references:
- 9f29234 publisher offline tests
- be3a0e7 isolated HTTP harness
- 9c44c25 website rollout notes
- d67da74 website snapshot reader
- f5e6940 website route
- d7f0bd3 optimized reader and tests

Do not put credentials, passwords, tokens or private connection secrets
into this handoff. Do not assume connected tools or host availability
will persist into a new conversation; rediscover and verify.

## 10. New-chat continuation instruction

Start by reading THIS file, docs/database-schema-reference.md,
docs/general-rankings-precompute-plan.md,
docs/general-rankings-freshness-decision.md,
docs/general-rankings-website-rollout.md,
migration 0026 and the actual publisher/reader/website files.
Reconcile historical docs with implementation. Inspect git status and
production/scratch identity before any DB operations. The immediate
unfinished task is the scratch full-scope writer benchmark, blocked by
a safety check on 2026-11-16. Do not claim it ran; proceed with authorized
tools or provide a controlled operator-run alternative. Then address
remaining rollout gates. NEVER repeat already completed work without
evidence that it is broken. NEVER infer schema from this prose alone.

## 11. UPDATE 2026-11-16 — benchmark blocker cleared (supersedes older status)

**New verified result:** The isolated RNT-01 full-scope writer benchmark DID run
successfully after the original handoff was authored. Earlier sections above
that say the benchmark was blocked or unmeasured are historical, superseded
by this update. Full details: docs/general-rankings-publisher-benchmark-20261116.md.

- Database: bf4ps_rank_scratch, port 5542, Alembic 0026.
- Scope: wins/all; 560,000 synthetic soldiers; generation 8 published.
- Elapsed: 6.690 seconds including commit.
- WAL: 205,249,944 bytes (195.74 MiB) during benchmark interval.
- general_rank_rows relation growth: 115,064,832 bytes (109.73 MiB).
- Publication pointer and actual inserted row count verified.
- No production deployment, no replica lag measurement. All other outstanding
  rollout gates remain, including repeated-cycle retention and 56-scope parity.

## 12. UPDATE 2026-11-16 — 56-scope scratch parity run completed

The guarded harness `player-collector/tests/scratch_general_rank_56_scope_parity.py`
completed with exit code 0 in 152.31 seconds, comparing all 56 scopes
against the legacy reader for four cases per scope. **56/56 passed.**
See `docs/general-rankings-56-scope-parity.md` for exact coverage.
Only 12 scopes had nonempty cohorts (kills, wins, time_played_seconds across
four platforms); the other 44 were empty due to missing synthetic metric
values. This does NOT establish populated-data parity for the other 11 metrics.
Generations 9–64 were added to scratch; production was untouched. The
next gate is a representative populated fixture for all 14 metrics plus
repeated-cycle retention, missing-pointer HTTP fallback and production health.

## 13. UPDATE — populated parity for all 56 combinations

The earlier 44 empty scopes have now been retested with populated synthetic data.
The new `player-collector/tests/scratch_general_rank_populated_parity.py`
seeded 1,200 scratch players across all 11 previously unpopulated metrics
and verified 44/44 populated scope comparisons against the legacy reader
(exit code 0, 16.15 seconds). Together with the prior 12 populated scopes,
all 56 combinations now have populated functional parity coverage. The 44
additional scopes used smaller cohorts (399–1,200 players) and are NOT
production-scale performance or replication evidence. See
`docs/general-rankings-56-scope-parity.md` for details. Remaining gates:
retention, HTTP missing-pointer fallback, operational scheduler, production
schema/health checks and a controlled production canary.

## 14. UPDATE 2026-11-17 UTC — bounded retention first scratch deletion

Opt-in `player-collector/bf4ps/general_rank_retention.py` now exists.
It deletes at most one completed unpublished generation per invocation,
requires a >=60-minute grace, protects the newest two completed generations
per scope and every published pointer, and uses the publisher's advisory lock.
On isolated RNT-01 scratch, one `--execute` call deleted obsolete generation 1.
Post-check: generation 1 absent, 56 published pointers intact, zero dangling
pointers. **NOT deployed to production, NO timer.** This is only one deletion;
cleanup throughput/WAL, repeat-cycle growth and replica impact are unverified.
See docs/general-rankings-retention.md. The next tasks are measured repeated
cleanup, HTTP missing-pointer fallback, and production-readiness checks.

## 15. CRITICAL UPDATE 2026-11-17 UTC — production deployment NO-GO

The scratch HTTP missing-publication-pointer fallback passed with flag ON and
restored generation 9. Three scratch retention deletions passed with measured
WAL intervals; see `docs/general-rankings-production-gate-20261117.md`.

**Production is NOT safe for general ranking migration/writer activation.**
MAK-DB-01 replica PostgreSQL is DOWN after disk-full WAL replay failure at
2026-11-17 16:43 UTC (0 bytes filesystem available). HNL-DB-01 has 6.3 GB
free and RNT-DB-01 has 2.6 GB free; both are still streaming on Alembic 0025.
KAH-DB-01 PostgreSQL has been stopped since October 22 and has only a 128 GB
root filesystem. MAK-DB-02 Desktop Commander agent is offline, but HNL's
receiver showed active primary streaming at 192.168.10.78:5432 at 21:10 UTC.
No production writes, restarts, or configuration changes were performed.
Prioritize production storage/replica incident resolution before any 0026
rollout. Full observations and guardrails are in the production-gate report.

## 16. UPDATE 2026-11-17 — one-scope cycle runner (no production activation)

New `player-collector/bf4ps/general_rank_cycle.py` chooses an unpublished
scope first or the oldest published scope, and with explicit `--execute`
serializes selection and one publication under the shared advisory lock.
Dry-run selected kills/all. Scratch execution published kills/all generation
153, population 560,000, exit 0, runtime 10.96 seconds. Five offline runner
tests passed; selected suite 21/21. No timer, daemon, fleet rollout, or
production database changes. See `docs/general-rankings-cycle-runner.md`.
Production storage/replica incident remains tracked separately; do not enable
unattended general publication until production readiness is independently
verified. Next: runner operational safety/monitoring, retention cadence,
repeat-cycle bounded storage test, and website as-of label.
