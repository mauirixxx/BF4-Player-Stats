# Precomputed equipment rankings — design checkpoint (2026-10-19)

## Verified baseline

Production PostgreSQL is at Alembic `0014_equipment_populations`. Live metric tables contain approximately 20.2 million weapon rows and 7.81 million canonical vehicle rows. `equipment_population` provides kind/item/platform population. `soldiers` provides identity and name; `player_exclusions` controls eligibility. The schema must be rechecked before migration implementation.

Read-only prototype, item 10 weapon and canonical vehicle family 2, PC, substring `mau`, 50 rows: kills, KPM, accuracy (weapons) and kills/KPM (vehicles) all matched legacy `soldier_id`, global `rank`, and deterministic `position`. Prototype calculation times were ~0.8–1.2s, versus legacy ~2–7s. These results do not establish parity across all platforms, items, null metrics, or excluded soldiers.

## Goals

- Search and filter equipment rankings without re-ranking full cohorts per HTTP request.
- Preserve `rank()` ties by metric value, `row_number()` position with `soldier_id` tie-break, canonical vehicle family consolidation, platform PC/PS/Xbox/ALL, population, percentile and division thresholds.
- Keep collector transactions independent of ranking refreshes.
- Publish only complete and validated ranking generations; retain the current API as fallback until proven.

## Proposed read model

A generation manifest tracks generation ID, scope (kind, canonical item, platform, metric), state (building/validated/published/retired), input watermark, creation/completion/publish times, row count, and parity status. Immutable generation rows store `(generation_id, soldier_id, rank, position)` with uniqueness on `(generation_id, soldier_id)` and `(generation_id, position)` and indexed lookups for rank and position. Metric values stay in existing transactionally maintained metrics tables; soldier names stay in `soldiers` so renames appear immediately.

Build one scope at a time in a staging generation, using one consistent database snapshot. Rank with `rank() OVER (ORDER BY score DESC NULLS LAST)` and `row_number() OVER (ORDER BY score DESC NULLS LAST, soldier_id)`. Exclude active player exclusions. Publish by atomically switching the manifest pointer in a short transaction, never exposing incomplete rows. Retain a previous generation for rollback, and garbage-collect older generations after a grace period.

**Important freshness constraint:** Rankings become stale as metric rows change. Serve generation timestamps and define a maximum permitted age; until the refresh interval and build cost are measured, do not claim current/instantaneous rank correctness. Keep existing live rank paths for stale/missing scopes. A generation must not be treated as fresh solely because it was recently published if the input watermark predates significant metric changes.

## Implementation gates

1. Verify authoritative schema and available ranking-worker deployment/repository; add an Alembic migration there, not ad-hoc DDL in production.
2. Benchmark one weapon and one vehicle generation in isolated scratch storage; record disk growth, locks, WAL, CPU, elapsed time, and concurrent collector impact.
3. Validate sample and edge-case parity (all platforms, metrics, ties, NULL scores, excluded soldiers, canonical SUM/MAX vehicle families, divisions, and pages).
4. Add atomic generation publication, freshness rules, retention, and read-only API feature flag; fallback on missing/stale/failed generation.
5. Soak refresh under continuous collector writes and demonstrate restart/recovery before production cutover.

## Scope control

Platoon fleet expansion, generic worker framework, and Discord stats bot remain separate future work. No Battlelog collection rate changes are needed for this feature.

## 2026-10-21 implementation update: catalog-wide bounded rollout

The production ranking service was located on **mak-01**, not the website host. Its `bf4ps-hourly-rank-builder.timer` and `bf4ps-rank-gc.timer` were both active, and the 08:00 UTC build successfully published 15 test scopes: weapon 10 and vehicle 1 on PC/PS4/Xbox, across their supported metrics. The live website on `tcou` already uses the opt-in precomputed reader with legacy fallback; the reader and guard have been restored into `website/api/` in Git commit `a459a03`.

The prior hourly runner hardcoded those two items. The consolidated `player-collector/hourly_runner.py` now enumerates catalog scopes from `equipment_rank_scope_versions` and `equipment_population`, including the `all` platform, and runs a **bounded, serialized, resumable** subset each hour. It skips recently refreshed scopes, prioritizes older published scopes and high-population missing scopes, and retains the advisory lock and independent publisher's production-ack, schema, population and version checks. The builder remains in `player-collector/build_rank_hourly.py`. Neither script calls Battlelog.

Safety defaults: 16 builds per run (`BF4PS_RANK_MAX_JOBS`, maximum 24), 900 seconds per run (`BF4PS_RANK_MAX_SECONDS`, maximum 1050), 120 seconds per build (`BF4PS_RANK_JOB_SECONDS`, maximum 180), and minimum population 1 (`BF4PS_RANK_MIN_POPULATION`). The website reader permits generations up to 10,800 seconds old; missing/expired/invalid generations fall back to existing queries. Large scopes may time out and must be measured before increasing budgets. Catalog-wide backfill is incremental, **not instantly complete**; verify database storage, WAL, GC retention, run times, and coverage before expanding throughput.

Operational checks: `systemctl status bf4ps-hourly-rank-builder.timer bf4ps-hourly-rank-builder.service`, `journalctl -u bf4ps-hourly-rank-builder.service -n 80 --no-pager`, and read-only SQL against `equipment_rank_published` joined to `equipment_rank_generations`. Check per-platform and per-metric counts, generation age, and parity against legacy rankings. Do not copy the ranking builder to all collector hosts: one active publisher per database is intentional.

Release gate: test the new runner on `mak-01` with a small bounded batch and confirm it publishes previously missing items (particularly AH-1Z/AH-6), then expand gradually. No migrations or Battlelog rate changes are part of this rollout. Preserve the old hourly runner for immediate rollback.

### Production rollout checkpoint — 2026-10-21 08:17 UTC

The catalog-driven runner's first production pilot on `mak-01` **passed**: weapon ID 5, platform `all`, metric `accuracy` published generation 164 with 139,026 rows in 39.53 seconds. Discovery found 964 item/platform catalog scopes and 2,609 missing/expired metric scopes. The original `hourly_runner.py` was backed up to `hourly_runner.py.pre-catalog-20261021`; the new runner was installed, syntax-checked and the existing enabled/active hourly timer retained. A new refresh cycle was started at 08:17 UTC. This is an **incremental rollout**, not a completed 2,609-scope backfill; watch the journal and storage growth before increasing the budget.

Rollback: restore the saved `hourly_runner.py.pre-catalog-20261021` to `hourly_runner.py` on `mak-01` between cycles; the existing timer will use the previous two-item plan at its next activation. Do not delete existing published generations. No other collector hosts need this script, and no Battlelog rate limits were modified.

### 2026-10-21 scheduler deadline correction

A 900-second cycle attempted its 16th scope with only ~39 seconds left, and the child was killed after ~34 seconds because the runner used `min(MAX_JOB_SECONDS, remaining-5)`. This was an artificial end-of-cycle timeout, not evidence that the SQL failed. The hourly timer remained active but the one-shot service exited nonzero. The runner now starts a new scope only when at least `MAX_JOB_SECONDS + 15` seconds remain; otherwise it logs a clean budget deferral and exits successfully (unless a previously attempted build actually failed). Previously committed generations remain published. This is a conservative deadline fix, not an increase to worker concurrency or Battlelog traffic.
