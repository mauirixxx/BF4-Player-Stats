# Isolated indexed ranking prototype results — 2026-10-18

Environment: mak-01, ephemeral `postgres:16-alpine` Docker container, private container network, scratch database `bf4ps_ranking_scratch`, synthetic deterministic 100,000 soldiers for weapon ID 5 and vehicle ID 1. No production schema/data changed; no Battlelog calls.

The script `scripts/performance/ranking_prototype.py` created scratch raw and derived tables, five btree indexes, and ran `EXPLAIN (ANALYZE, BUFFERS)` against equivalent Top 10 queries. All five exact identity/score comparisons passed.

| Metric | Unindexed execution ms | Derived indexed execution ms | Ratio |
| --- | ---: | ---: | ---: |
| Weapon kills | 28.380 | 0.084 | 338x |
| Weapon KPM | 81.653 | 0.081 | 1008x |
| Weapon accuracy | 80.963 | 0.091 | 890x |
| Vehicle kills | 27.752 | 0.094 | 295x |
| Vehicle KPM | 81.252 | 0.088 | 923x |

Indexed plans used `Index Only Scan`, with 10 heap fetches on the freshly built tables. Results are single-run measurements on synthetic data, not production latency predictions. Actual production leaderboard performance includes platform/state eligibility, player exclusions, vehicle-family SUM/MAX consolidation, global tie ranks, population and percentiles; **none of those have yet been parity-tested against the derived read model**. The isolated test also did not rehearse the full Alembic 0001–0012 migration chain or measure collection-time maintenance cost.

Next gates: (1) full Alembic scratch replay, (2) audited vehicle-family consolidation and eligible cohort parity, (3) bounded restartable PostgreSQL-only backfill, (4) collector transactional dual-write, (5) feature-flagged website cutover. Production remains on revision `0012_manual_verify_api`.
