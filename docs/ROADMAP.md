> **2026-10-21 update:** Both `mak-05` and `hnl-03` platoon timers are now active and have completed live work using the shared UUID lease. The October 19 pending platoon-worker deployment items below are historical; sustained two-node failover/soak testing remains outstanding. See [path-to-completion.md](path-to-completion.md).

# BF4 Player Stats — Project Roadmap

**Last consolidated:** 2026-10-19
**Status:** Working project index and priorities. This document organizes the project roadmap; detailed designs and historic benchmarks remain in their original files.

> **Source of truth:** Preserve the full [Performance and Feature Roadmap](PERFORMANCE-OPTIMIZATION-ROADMAP.md), originally maintained on `release/website-2026-10-15`. Its October 15 measurements and completed/unchecked milestones are a historical baseline, **not** a claim that all work listed below was already in GitHub. Keep this index updated as work lands. Refer to documented schemas and verify them against production before writing database SQL.

## Current sprint — in priority order

- [x] **Deploy indexed Top 10 equipment rankings and population counters.** Weapon/vehicle Top 10 endpoints improved substantially; observed public API responses on selected simple items were approximately 75–115 ms. Use measured, item-specific benchmarks rather than assuming every vehicle family has this performance.
- [x] **Restore the production distributed stats fleet and add `hnl-03`.** Nine BF4PS statistics collectors (mak-01/02/03/04, hnl-01/02/03, rnt-01, kah-01) verified collecting as of October 19. `tcou` is website-only. `mak-05` is the dedicated platoon worker.
- [ ] **Finish no-migration equipment player lookup optimization.** Partial-name and persona-ID searches must return exactly the same matches, global rank, position, percentile, tie handling, division, and platform behavior as the existing API, without re-ranking the whole cohort twice. Preserve exclusions and the fast Top 10 path. Candidate tested for weapon/vehicle kills, weapon accuracy and vehicle KPM; **weapon KPM parity failed** and must be reconciled before production. Test null rates, multiple matches, all three platforms, ALL, matching aliases where applicable, and concurrent collections. Use schema revision `0014_equipment_populations` and the real deployed query semantics; no Alembic upgrade expected unless new indexes or data structures prove necessary. Prefer branch/PR, benchmarks, rollback, and staged validation.
- [ ] **Admin-only queued-platoon lookup and near-front refresh.** Place a dedicated queue search panel below Collection Overview. Search **only queued platoons** by platoon ID/name/tag and display matching queue status. Reuse the existing manual request/refresh path and scheduling semantics rather than introduce a priority column. Determine whether re-requesting an already pending item genuinely advances it; avoid implying immediate processing if it does not. Do not interrupt running jobs, ignore retry safeguards, or bypass request budget. Validate administrator authorization, CSRF protection, auditable actions and read/write DB privileges.
- [ ] **Make platoon and soldier-to-platoon discovery safely multi-node.** Current `mak-05` scripts select work then separately mark it running; this is **not** safe with two workers. Design and implement atomic claim/lease/reclaim/expiration, idempotent completion, cooldowns, cross-site coordination, and bounded shared Battlelog pacing. Decide whether an Alembic migration is warranted **after** examining the authoritative schema and live DB. Run concurrency/crash/failover tests.
- [ ] **Deploy a second platoon worker on `hnl-03` alongside `mak-05`** only after the preceding coordination work passes tests. Retain its already-operational stats collector independently; verify neither site double-claims work.
- [ ] **Optimize consolidated vehicle-family rankings**, preserving canonical family SUM/MAX rules for multiple raw IDs. The October 19 Top 10 indexed shortcut deliberately falls back to legacy aggregation for families with multiple raw IDs.
- [ ] **Synchronize deployed October 18–19 fixes to a reviewed GitHub branch/PR.** Check collector exclusion filtering, production schema preflight revision, ranking/population transactional flags, nine-host deployment documentation, and the website Top 10 optimizations against the actual running revisions. Do not claim a deployment is committed upstream without verification.

## Performance and database follow-ups (from original roadmap)

Retain the original roadmap's full technical checklist, including:
- [ ] Browser initial render / JSON parsing / DOM CPU / memory, payload measurements, and uncached/repeated-visit p50/p95 benchmarks.
- [ ] Equipment leaderboard endpoint, cache and pagination audit; revise [Leaderboard Pagination, Cache and Selection Design](LEADERBOARD-PAGINATION-CACHE-SELECTION-DESIGN.md) where its scratch-only assumptions no longer apply.
- [ ] Safe bounded EXPLAIN (ANALYZE, BUFFERS) of measured slow paths; index/TOAST/table-size review, autovacuum and write-churn diagnosis.
- [ ] Database pooling, `max_connections=300`, production HA/failover and collector impact review without blind tuning or restarts.
- [ ] Collector admission pacing, retry/backlog health, identity/alias integrity and incremental community aggregate freshness.

**Previously completed in the source document:** replacement of the 151.4 MiB recurring homepage snapshot download with bounded/summary-based pages and lightweight refresh; initial database audit; search and alias-aware general leaderboard work; feature-flagged benchmarks and rollback. See [Homepage Production Cutover](HOMEPAGE-PAGINATION-PRODUCTION-CUTOVER.md) for the October 15 evidence.

## Product and experience backlog (from original roadmap, preserved)

- [ ] **Equipment artwork:** inventory Battlelog fancy/HUD assets, canonical mappings, fallbacks, licensing/source validation, safe storage/cache and updates. Partial implementation/admin controls exist, but do not mark the original end-to-end checklist complete without acceptance checks.
- [ ] **Administrator experience:** Discord OAuth design, allowlisted roles, least privilege, session/CSRF/audit enforcement, safe artwork replacement and rollback. The existing admin login is not proof Discord OAuth is implemented.
- [ ] **Platoon statistics:** research Battlelog pages/rate limits/failures; define member identity, sync/historical membership semantics and manual overrides; implement platoon-only combined statistics with deduplication and tests. Existing platoon discovery is a partial implementation, not completion of this wider scope.
- [ ] **Discord statistics bot:** design `/stats <player>`, cross-platform disambiguation, alias presentation, embeds, read-only API access, caching, permissions, hosting and outage handling; prototype before production.
- [ ] **Future player comparisons:** comparison UX and, where practical, cross-platform combined views with manual account associations explicitly labeled and verified. This is a future extension, not an implemented capability.

## Operations, documentation, and release discipline

- [ ] Maintain a reproducible collector release/image with explicit versioning, deploy/rollback procedure, registry of all nine stats nodes, and independent platoon-worker roles.
- [ ] Establish production service recovery checklist: leaderboard, admin/moderation, manual request, platoon admission, website exports, platoon discovery timer. The October 19 maintenance recovery exposed disabled APIs and a read-only privilege gap.
- [ ] Document and validate equipment ranking metric/materialized-table parity as collectors update rows; ensure population totals respect exclusions.
- [ ] Keep dated evidence of actual latency and query correctness; do not conflate a fast, cached Top 10 with slower search, division or deep-page requests.
- [ ] Maintain source-of-truth schema documentation and periodically verify against production. Where the October 15 roadmap points to `docs/database-schema-reference.md`, check the active branch's schema docs before applying changes.
- [ ] Continue development through feature branches and reviewed PRs, with tested rollback. Preserve existing website artwork modifications and other uncommitted deployment work when changing ranking code.

## Deployment inventory (verified in conversation October 19, 2026)

| Node(s) | BF4PS role | Status at last verification |
| --- | --- | --- |
| mak-01, mak-02, mak-03, mak-04 | Statistics collectors | Nine-node fleet verified |
| hnl-01, hnl-02 | Statistics collectors | Nine-node fleet verified |
| hnl-03 | Statistics collector; **future** secondary platoon worker | Stats collecting; platoon role not deployed |
| rnt-01, kah-01 | Statistics collectors | Nine-node fleet verified |
| mak-05 | Primary platoon roster / soldier discovery | Timer restored, successful work verified |
| tcou | Website and public/private APIs | Website-only (no stats collector) |

This is a dated operational snapshot, **not** a live health monitor.

## Reference documents

- [Original performance and feature roadmap](PERFORMANCE-OPTIMIZATION-ROADMAP.md)
- [Homepage performance benchmark](HOMEPAGE-PAGINATION-BENCHMARK-2026-10-15.md)
- [Homepage production cutover and verification](HOMEPAGE-PAGINATION-PRODUCTION-CUTOVER.md)
- [Leaderboard pagination and caching design](LEADERBOARD-PAGINATION-CACHE-SELECTION-DESIGN.md)
- [Manual player refresh design](MANUAL-PLAYER-REFRESH-DESIGN.md)
- [Equipment source of truth](EQUIPMENT-SOURCE-OF-TRUTH.md)
- [Community statistics design](COMMUNITY-STATS-v1.md)
- [Original discussion and future feature ideas](https://github.com/mauirixxx/BF4-Player-Stats/issues/1)

**Update policy:** after each milestone, record actual GitHub branch/PR/commit, production validation results, any remaining gaps, and rollback method. Keep the old performance roadmap for historical measurements instead of silently overwriting completed benchmarks.
