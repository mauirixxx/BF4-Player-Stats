# Homepage pagination: production cutover and verification

**Status: deployed and verified, 2026-10-15 (Hawaii local date).** Feature branch: `feature/homepage-paginated-data`; cutover commit `0f5bc93`. This records the deployed homepage data path, not a claim that all database tuning is complete.

## Before and after

- Previous homepage: fetched `/temp-stats-data.json` on initial load and every 60 seconds, transferring a roughly 167–173 MB uncompressed JSON snapshot containing hundreds of thousands of soldier rows. User observed 2–3 seconds on F5 over LAN.
- Current homepage: `/homepage-summary.json` for counters (264–265 bytes observed) plus `/bf4ps-api/general-leaderboard` for 50 leaderboard rows (~14.6 KB observed); `/bf4ps-api/global-soldier-search` only for searches. User reports practically instant F5 and minimal delay switching platform/equipment selectors.
- PostgreSQL computes ranking, pagination and filters; the browser no longer loads the entire soldier collection. Existing weapon/vehicle leaderboard endpoints remain in use.
- **Do not remove the legacy JSON export**: soldier detail and temporary dashboard consumers still use it.

## Verification and deployment

1. Python suite: 21 tests passed; Node adapter and simulated-DOM staging runtime tests passed. These are not substitutes for real-browser testing.
2. Legacy-versus-live top-50 rankings compared for kills, wins, score and playtime: 200/200 positions matched at test time.
3. Staging URL `/index-paginated-staging.html` was user-tested in Firefox; fast refresh and minor selector latency reported.
4. `bf4ps-temp-dashboard.service` restarted to activate atomic compact summary output; output file verified on disk. `bf4ps-leaderboard-api.service` restarted to activate the new read-only API routes. Both services subsequently reported active.
5. Production `site/index.html` promoted from the tested staging file, committed as `0f5bc93`, and installed to `/var/www/bf4playerstats.com/index.html`. HTTPS origin checks returned 200 for index, summary and leaderboard; deployed index confirmed to reference `homepage-paginated.js` and not `temp-stats-data.json`.
6. Cloudflare returned 1010 when probed from the server through the public hostname; origin checks used `curl --resolve www.bf4playerstats.com:443:127.0.0.1` to preserve TLS SNI and bypass Cloudflare. The user separately tested the live browser experience.

## Rollback

- Production pre-cutover HTML: `/var/www/bf4playerstats.com/index.html.rollback-20261015-1519` (also `site/index.html.rollback-20261015-1519` in the server worktree; untracked backup). If required, restore the production backup to `/var/www/bf4playerstats.com/index.html`, then verify HTTP 200 and the expected old bulk-JSON reference.
- Keep `/temp-stats-data.json` and its exporter running so rollback remains functional. Reverting only the homepage HTML is sufficient for the frontend cutover; no database schema change was made.
- Feature branch retains the tested code and API implementation; do not roll back the API service unless there is a separate API regression.

## Follow-up, not release blockers

- Database performance: inspect query latency/p95, plans, autovacuum and connection use **only if real monitoring reveals a problem**; avoid speculative indexes or tuning. Existing API read-only query timeout remains a safety guard.
- Profile/soldier-detail and temporary dashboard still consume the legacy snapshot; optimize independently when justified.
- Deep-link persona lookup uses substring search with a one-row response and could select an overlapping persona ID; harden with exact persona lookup when revisiting deep links.
- Test under realistic concurrent visitors and add lightweight latency monitoring before declaring broader scaling guarantees.
- Reconcile the deployed optimization branch with the official release branch and confirm future deployment source-of-truth.
