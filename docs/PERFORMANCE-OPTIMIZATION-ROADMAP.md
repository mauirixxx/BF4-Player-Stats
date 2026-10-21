# BF4 Player Stats — Performance and feature roadmap

Status: **Homepage performance milestone deployed 2026-10-15; remaining database work is observation-driven, not a release blocker.** Baseline measured 2026-10-15. This document is the working checklist; update it as milestones pass. Consult the authoritative database schema and verify against production before writing SQL.

## 1. Database and homepage performance — PRIORITY

- [x] Identify initial-load bottleneck: homepage downloads `/temp-stats-data.json` (~158,737,575 bytes / 151.4 MiB), including ~200k soldier rows, on initial load **and every 60 seconds** with a cache-busting query string. Measured on tcou: ~3.92 seconds for the transfer (server-side test), excluding client JSON parsing and rendering. `index.html` ~38.5 KB / 0.25 sec; API health ~0.09 sec.
- [x] Record initial database snapshot: `bf4_playerstats` ~2,832 MB, weapon stats ~4.24M rows, vehicle stats ~2.02M, soldiers ~206k estimated by pg_stat_user_tables; these estimates differ from exact website counts. No changes made during baseline audit.
- [ ] Instrument and benchmark browser initial render (network transfer, JSON.parse, DOM/render CPU, memory), API p50/p95, query time, and payload sizes. Test uncached and repeated visits from a remote browser.
- [x] Design a compact homepage summary endpoint and bounded server-side general leaderboard pages (default 50), retaining all metrics, stable ties, division cutoffs, platform filtering, deep links, and existing user-facing behavior.
- [x] Move global search and alias-aware lookup fully server-side; preserve persona ID lookup and name aliases. Validate pagination/search correctness with ties and division boundaries.
- [x] Implement cacheable/snapshot-backed summary and 60-second lightweight refresh, eliminating the huge recurring download. Consider compression only as a stopgap; do not rely on compression as the architectural fix.
- [ ] Audit equipment leaderboard endpoint, caching and pagination against current deployed implementation; update the older `LEADERBOARD-PAGINATION-CACHE-SELECTION-DESIGN.md` assumptions (D3-only proposal is outdated).
- [ ] Review EXPLAIN (ANALYZE, BUFFERS) safely for slow queries; inspect index usage, query plans, statistics, and table/index/TOAST sizes. Never run unbounded expensive production EXPLAIN without a statement timeout.
- [ ] Review PostgreSQL autovacuum and write churn (collection_jobs ~144k estimated dead tuples); investigate unusually large soldiers/soldier_names/catalog storage and profile_soldiers sequential scans. Verify real cause before altering indexes/settings.
- [ ] Review connection pooling, max_connections=300, HA failover and collector impact. Prefer read-only changes; no blind tuning or restarts.
- [x] Build automated regression/performance tests, feature-flag rollout, rollback instructions and before/after benchmarks. Confirm collectors remain unaffected.

See [production cutover and verification](HOMEPAGE-PAGINATION-PRODUCTION-CUTOVER.md) for measured results, deployed endpoints, test coverage, rollback, and deferred database tuning. Remaining unchecked performance audits are optional, to be prioritized from real observed latency or operational issues.

## 2. Collection reliability and data quality

- [ ] Review collector admission pacing, retries, throughput, backlog, and failure recovery.
- [ ] Validate identity/alias deduplication and cross-platform separation.
- [ ] Verify incremental community aggregate freshness, completeness semantics and snapshot scheduling.

## 3. Weapon and vehicle images

- [ ] Inventory Battlelog assets for both **fancy** and **HUD** variants; confirm rights and source availability.
- [ ] Map assets to canonical catalog IDs, including aliases/duplicates, and define fallbacks.
- [ ] Implement image storage, caching, review and safe updates.

## 4. Administration / Discord authentication

- [ ] Design Discord OAuth login, allowlisted roles, least privilege, session security, CSRF, audit logs.
- [ ] Admin artwork upload/replace and metadata editing with validation, previews and rollback.

## 5. Platoons — design documented, implementation pending

**Design contract:** [PLATOON-SUPPORT-DESIGN.md](PLATOON-SUPPORT-DESIGN.md). Team Wired roster inspected read-only 2026-10-18; no schema migration or production import yet.

- [x] Document official-membership-only multi-platform model, schema, importer, UI, aggregates and staged verification.

### 5.1 Remaining implementation research

- [ ] Research Battlelog platoon pages, membership import, rate limits and failure behavior.
- [ ] Design identity matching, membership sync, manual override and historical membership semantics.
- [ ] Design platoon-only combined statistics using collected data; validate deduplication and performance.

## 6. Discord statistics bot — discussion and testing first

- [ ] Design `/stats <player>` UX, disambiguation, platform, aliases, embeds and permission model.
- [ ] Design read-only API access, caching, rate limits, outage handling and hosting.
- [ ] Prototype and test before production deployment.

## Guardrails

- Preserve current homepage appearance and behavior unless explicitly approved.
- Never grant website write access to collector tables for performance changes.
- Consult `docs/database-schema-reference.md` (authoritative) and verify actual live schema before SQL modifications.
- Prefer a feature branch / PR, reversible deploy and measured results. Do not deploy an untested data-path rewrite to production.
- Production database access uses `db.bf4statusbot.com`, never a hardcoded individual DB node.
