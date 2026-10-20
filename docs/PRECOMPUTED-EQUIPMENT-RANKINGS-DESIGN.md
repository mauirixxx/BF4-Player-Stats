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
