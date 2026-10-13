# BF4PS Website Hardening — Design v0.1

Status: design approved in principle; implementation and deployment pending. Source: WEBSITE branch, 2026-10-13 tcou audit.

## Scope and invariants
- BF4PS website only; do not change other Apache virtual hosts, BF4 Server Watcher, or collectors.
- All tests remain on `bf4ps_scratch_stage9c_d3`; preserve both existing database-name safety guards until an explicit production cutover.
- Never store credentials or generated soldier data in Git.
- Do not modify live tcou files/services until the branch has been reviewed and a rollback prepared.

## Current state (verified)
- `site/index.html`: static leaderboard frontend.
- `api/leaderboard_api.py`: Python ThreadingHTTPServer on localhost:8765, SQLAlchemy pool_size=3, max_overflow=2, pool_pre_ping=True. Per-item leaderboard returns all matching soldiers; API sends Cache-Control: no-store; database failures return HTTP 500.
- `api/temp_dashboard_export.py`: exports JSON to web root every five seconds, re-querying multiple tables; scratch-only.
- Both systemd services run as root with D3 env file. Apache serves multiple unrelated sites.
- Source branch WEBSITE is a development snapshot, not production-ready.

## Maintenance mode — application-owned, no Apache configuration changes
- Configuration outside web root, e.g. `/etc/bf4ps-website/site.env` (root-owned, mode 0640), with `MAINTENANCE_MODE=false` or `true`.
- A shared application configuration/status endpoint must reflect flag changes without requiring a restart, and must not need PostgreSQL to read the flag. Parse only explicit true/false; invalid/missing configuration must have documented fail behavior and logs.
- Both frontend and all BF4PS API routes must honor maintenance. The frontend must check status *before* fetching statistics or rendering the normal interface, and show a full-screen maintenance view. Recheck on tab focus and at a bounded interval. API responds 503 with JSON for API clients; include Cache-Control: no-store and Retry-After.
- Static HTML is still delivered by Apache: without changing Apache or serving the page through the application, application-level frontend maintenance is a client-side replacement, **not** a server-side HTTP 503 for the HTML document. Accept this distinction explicitly or revisit architecture if HTML-level 503 becomes mandatory.
- If the API or DB is unavailable, frontend shows the same friendly page. Avoid interpreting a single transient network error as permanent; retry with backoff and recover automatically.
- No protected admin endpoint in v1; Discord OAuth authorization is future work. Do not expose a public writable maintenance toggle.
- Verify both manual and automatic modes, including API unavailable, DB unavailable, and restoration. Do not intentionally interrupt shared production PostgreSQL.

## Performance and resilience
1. Add bounded request concurrency (ThreadingHTTPServer currently spawns unbounded threads). Use a bounded worker server or gateway limits, independent of DB pool.
2. Add explicit query timeouts, pool_timeout, and defensive error classification; do not leak SQL or credentials in HTTP errors.
3. Paginate per-item rankings (bounded limit, deterministic sort, total count), update frontend consumption; never return all matching soldiers.
4. Cache read-only leaderboard responses by normalized query key for a configurable short TTL (initial proposal 30s). Limit cache entries/bytes and prevent cache stampedes. Maintenance bypasses cache.
5. Review indexes using actual D3 schema and EXPLAIN (ANALYZE, BUFFERS) under safe limits before writing migrations. Preserve UCAV 10/54 canonicalization semantics.
6. Replace five-second full-table JSON export with bounded summary or incremental snapshot approach, after measuring actual costs.
7. Use dedicated non-root service identities with minimal filesystem and read-only DB permissions; review systemd restart and resource limits.
8. Keep Apache changes out of maintenance implementation; consider static asset compression/caching separately, scoped strictly to BF4PS vhost.

## Load test and acceptance
- Baseline response latency, throughput, DB connections, CPU/memory, query plans, payload size and error rate.
- Run from a separate load generator; increase gradually 50 -> 100 -> 250 -> 500 -> 1000 simulated concurrent users with realistic navigation and think times.
- Do not test 1000 against live tcou/shared DB without explicit resource budget and approval; use isolated staging or capped tests first.
- Acceptance: bounded DB connections, no unbounded memory/thread growth, no 500s for controlled maintenance, correct pagination/canonicalization, other tcou sites unaffected.

## Delivery sequence
A. Add tests and application maintenance flag/status contract, frontend maintenance experience, graceful 503 behavior.
B. Bounded concurrency, query timeouts, pagination and caching with regression tests.
C. D3 schema/index verification and exporter optimization.
D. Controlled load test, deployment runbook and rollback; production cutover separately authorized.

## Rollback
- Preserve WEBSITE deployment snapshot and systemd unit files before changes.
- Test changes on separate port/docroot first; never overwrite live site as a development shortcut.
- Roll back by restoring previous service code/config and restarting only BF4PS services; never alter BF4SW services.
