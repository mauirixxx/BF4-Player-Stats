# General soldier rankings: precomputed publication plan

Status: implementation design, NOT deployed. Baseline: BF4PS Alembic 0025, live general_leaderboard.py verified 2026-11-15.

## Contract

- 14 metrics (`kills`, `total_score`, `wins`, `time_played_seconds`, `conquest_score`, `rush_score`, `team_deathmatch_score`, `domination_score`, `obliteration_score`, `defuse_score`, `capture_the_flag_score`, `air_superiority_score`, `carrier_assault_score`, `chain_link_score`) times 4 platforms (`all`, `pc`, `ps4`, `xboxone`).
- Rank the complete eligible cohort before search, division and pagination. Preserve SQL `rank()` ties, deterministic `row_number()` order (`value DESC, soldier_id`), and division cutoffs 3/8/15/25/35/50/65/80/90 percent.
- Eligibility: successful detailed collection, non-null metric, active player exclusions omitted. Source: `soldiers`, `collection_state`, `detailed_stats_current`, `player_exclusions` (see `database-schema-reference.md`).
- Preserve `hours_source_seconds`, current soldier names, persona IDs, aliases, country/flag and platoon presentation. Dynamic identity metadata must be joined at read time, not frozen in immutable ranking rows.
- New general-only generation/published pointer tables; do not reuse equipment generation/retention lifecycle. A failed build cannot replace a good published generation. Publishing is a single transaction with fencing against stale workers.
- Reader must return exact existing JSON contract: population, filtered_count, total_pages, rank, position, top_pct, division, 50 rows. Search and division apply after global rank. Empty/out-of-range pages retain accurate metadata.
- Full dataset (~560k eligible soldiers at 2026-11-15) must remain pageable, not just top 50. Read path must avoid reranking the population per request.

## Rollout gates

1. Reconcile current production catalog and Alembic head with schema reference; design additive 0026 migration and schema-reference update together.
2. Build bounded generation writer and indexes; benchmark WAL, replication lag and storage on scratch before production.
3. Compare all 56 metric/platform scopes against the existing live SQL, including tied scores, divisions, aliases, empty pages and exclusions. Run update/retention concurrency tests.
4. Publish one canary scope, compare API responses and page counts, then enable a guarded reader with immediate legacy fallback. Observe production and roll out all scopes.
5. Retire live ranking fallback only after parity, freshness and operational monitoring pass. Preserve existing equipment publishers and retention throughout.

## Current state

The live general leaderboard was optimized to one SQL statement with materialized ranked/filtered CTEs on 2026-11-15. Cold production request still took 6.50 seconds; cached default Top 50 requests are faster. No general ranking precompute migration or publisher has been deployed yet.
