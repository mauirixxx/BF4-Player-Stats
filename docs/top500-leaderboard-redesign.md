# Top 500 leaderboard redesign — design proposal (2026-10-27)

Status: **DESIGN ONLY**. Branch: `top500`. No production schema, query, worker, or website changes authorized by this document.

## Decision and motivation
Replace full hourly immutable ranking generations with bounded **Top 500** leaderboards. Current snapshot generation/replacement and retired-generation cleanup created substantial ranking-table storage, dead tuples, WAL, and replica catch-up pressure. Preserve fast reads while scaling toward 1M+ and eventually 6M soldiers.

## User-facing contract
- Weapon metrics: kills, KPM, accuracy. Vehicle metrics: kills, KPM.
- PC, PlayStation, Xbox each expose the top 500 eligible soldiers for every equipment/metric; ALL shows the global top 500 across the three platforms.
- Ranks 1–500 are shown. Outside Top 500: **Outside Top 500** (no exact global rank). Not eligible: **Not qualified**.
- Keep full personal weapon/vehicle stats, top-10 defaults, paginated leaderboards, eligibility/minimum-use filters, moderation exclusions, deterministic tie handling, and fast website responses.
- Total eligible population and division/percentile presentation require a separate product decision: do not silently change or invent these semantics.

## Preferred architecture to test
1. **First benchmark direct indexed reads** from current weapon/vehicle statistics or current leaderboard metrics; do not assume another persistent ranking table is needed.
2. Use per-equipment descending metric indexes with stable tie-breaks and all required eligibility/platform predicates; validate query plans and actual timing for top 10, top 50 pages, and top 500.
3. For ALL, merge the platform-specific top 500 candidates and take global top 500 using the same total ordering. Mathematical guarantee requires consistent eligibility, tie-breaks and platform partitioning; handle cross-platform soldier identity according to existing product semantics.
4. Qualification/promotion occurs automatically on subsequent reads when underlying statistics change. Demotion, exclusions, corrections and deletions also reflect source truth; no manual leaderboard slot replacement.
5. Keep existing 5-minute cache/coalescing where appropriate; invalidate or expire safely. If direct queries fail performance budgets, consider bounded cached Top-N materialization maintained incrementally, **not** complete immutable full-population generations.
6. If population metadata is needed, design compact counts/aggregates separately; avoid exact ranks for unranked soldiers.

## Verified starting points
- Consult `docs/database-schema.md`, `docs/operational-schema.md`, dated live catalog and Alembic migrations before implementation. Latest previously observed production Alembic revision: `0018_distributed_rank_queue`; reconfirm live.
- Live PostgreSQL indexes observed 2026-10-27: `ix_weapon_leaderboard_metrics_{kills,kpm,accuracy}_top`, `ix_vehicle_leaderboard_metrics_{kills,kpm}_top`, and `ix_soldier_weapon_stats_weapon_kills`. Their current definitions do **not** establish that all platform/eligibility predicates are optimally indexed.
- Prior ranking table ~97 GB, ~427M estimated live rows; these were snapshots, not measurements of proposed design.
- Production ranking builder remains **stopped**. Hourly bounded retired-generation GC currently limited to one generation per hour; do not resume builder as part of this design.

## Benchmark and migration gates
1. Read and reconcile documented and live schema, deployed ranking SQL, website query paths, eligibility, ties, and ALL semantics.
2. Run EXPLAIN (ANALYZE, BUFFERS) read-only on representative popular/sparse equipment and each metric/platform; use safe statement timeouts. Compare Top 10, Top 500, paginated Top 500, ALL merge, and name search.
3. Measure p50/p95 latency, buffer hits/reads, CPU, query plans, replica lag, WAL and table/index storage. Test with realistic 100K, 1M and 6M scale assumptions; do not extrapolate uncritically.
4. Validate exact parity for eligible Top 500 and tie ordering against known published rankings; separately reconcile known stale snapshot effects and moderation filters.
5. Introduce new read path behind feature flag, retain rollback; stage rollout and monitor. Avoid adding indexes to production without checking disk/WAL and replication capacity.
6. Once verified, retire old generation writer, old read path, and generation tables in a **separate reviewed cleanup**; do not drop production tables while replicas are recovering.

## Open decisions
- Top 500 pagination UI and whether to expose all 500.
- What happens to percentile/division labels and population counts.
- Cross-platform duplicate identity policy in ALL.
- Freshness/caching policy and acceptable latency target.
- Whether bounded Top-N cache/materialization is necessary after direct-read benchmarks.

## Operational guardrails
- Never restart full-snapshot precompute during replica recovery.
- Preserve collection throughput and existing published leaderboards until replacement is validated.
- Explicit WAL/replica-lag guardrails and staged deployment before any production index build.
