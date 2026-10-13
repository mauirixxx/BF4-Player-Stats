# Leaderboard pagination, caching, and equipment-selection design

Status: **Design proposal — no production deployment authorized**.

## Goals
1. Preserve equipment selection when switching platform tabs; remember the last selected weapon and vehicle independently.
2. Move equipment leaderboard paging from client-side full-result download to SQL-backed paging, while retaining global search, division filtering, stable ranks and population counts.
3. Reduce repeated read-only database queries through bounded caching.
4. Benchmark 1k, 5k and 10k soldiers using only the approved D3 scratch database.

## Current behavior (verified against WEBSITE code)
- `site/index.html`: `loadUnifiedEquipment()` recreates the equipment dropdown after each platform change, implicitly selecting the first catalog item.
- `api/leaderboard_api.py`: `GET /leaderboard?kind=weapon|vehicle&platform=...&item=...` returns **all** matching soldier rows, sorted by kills descending and soldier_id. The frontend ranks and pages this array.
- Catalog queries limit to 400 items; vehicle ID 54 is canonicalized to 10 for duplicate UCAV records, with per-soldier `MAX(kills)` rather than summation.
- API refuses connections to any database other than `bf4ps_scratch_stage9c_d3` and runs equipment reads in a read-only transaction.

## UX contract
- Preserve equipment by canonical catalog ID when changing platforms; if missing, select first available item and show no stale selection.
- Keep separate remembered IDs for weapon and vehicle, including when switching between metric categories.
- On equipment, platform, search or division-filter changes, reset page to 1. Next/previous paging must not alter selections.
- Do not persist selections in browser storage in the initial implementation.
- Use request-generation tokens to ignore stale responses when tabs or equipment change rapidly.
- Preserve the current division definition and tied-rank semantics. Never calculate global rank from a single page alone.

## API contract (proposed, backward compatible)
- Catalog mode (no `item`) retains current response shape initially.
- Item mode gains optional validated `page` (1-based, default 1), `page_size` (default 50, maximum 100), `search`, and `division` parameters.
- Response: `population` (eligible population before search/division), `filtered_count`, `page`, `page_size`, `total_pages`, and `rows` with global `rank`, `division`, `top_pct`.
- Filtering by division uses rank/population calculated across the complete eligible cohort; search applies to name/persona ID on the selected platform. Tied kills retain shared ranks, with deterministic soldier ID secondary ordering.
- Out-of-range pages return an empty rows array and accurate pagination metadata. Invalid parameters return HTTP 400.
- Avoid a full-row fetch to Python. Prefer window functions / CTEs for ranking and filtering, then LIMIT/OFFSET. Verify query plan and documented schema before implementation.
- Maintain current 503 behavior, maintenance toggle, no-store headers, D3-only guard and SELECT-only transactions.

## Caching design (proposed)
- Cache catalog responses and bounded equipment ranking page results, keyed by canonical query parameters (kind, platform, item, page, page_size, search, division).
- Start with a 30-second TTL and strict maximum entries/bytes, measured and adjusted during benchmarks.
- Use lock-protected cache operations for ThreadingHTTPServer. Avoid caching 503/error responses. Maintenance check must run **before** any cache lookup.
- Document staleness and cache invalidation; no cache bypass of D3 database identity guard. Verify cached responses cannot leak between distinct queries.
- Provide cache-hit/miss and request-latency metrics without exposing personal data.

## Schema and validation gate
Before coding SQL, consult the repository's schema documentation and compare it against the **live D3 scratch schema** with read-only metadata queries. Specifically verify `soldiers`, `collection_state`, `soldier_weapon_stats`, `soldier_vehicle_stats`, `weapon_catalog`, `vehicle_catalog`, indexes and constraints. Record differences; do not infer column names from memory.

## Testing and rollout
1. Implement equipment selection independently; unit-test platform switches, category switches, missing catalog IDs, rapid changes.
2. Build read-only SQL paging tests: ties, population/division boundaries, searches, empty results, UCAV canonicalization, and query validation.
3. Load-test 1k / 5k / 10k cohorts in isolated D3 scratch; record p50/p95 latency, response size, query count, memory and cache hit ratio. Do not modify production BF4SW or its identity-import pipeline.
4. Test through isolated ports 8766/8877, maintenance on/off and API failure recovery; compare against the existing website.
5. Promote via PR into WEBSITE only after validation, with backup and rollback steps.

## Separate BF4SW identity-import checkpoint
The operator reports the 200k+ name pull has completed. Independently inspect importer final report, counts by platform, distinct persona identities, duplicate/alias handling, failure/retry totals and checkpoint. **Do not assume the name import populates detailed stats**. No writes to BF4SW production.
