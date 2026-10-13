# BF4 Player Stats — WEBSITE branch

This branch preserves the **actual deployed website sources** from `tcou` (2026-10-13) separately from the collector release. It is a development snapshot, **not yet a standalone production deployment**.

- `site/index.html`: Battlelog-inspired leaderboard and soldier-search frontend.
- `site/temp-stats.html`: temporary collection monitor.
- `api/leaderboard_api.py`: read-only weapon/vehicle ranking HTTP endpoint.
- `api/temp_dashboard_export.py`: temporary read-only JSON snapshot exporter.

The two Python services currently contain deliberate checks requiring `bf4ps_scratch_stage9c_d3`. Preserve those safety guards until a reviewed, configurable production database target is implemented. The exporter emits `temp-stats-data.json` into the Apache document root; **never commit this generated data** (it contains player identities/statistics). Credentials must come from the environment and never enter the web root. The frontend expects `/bf4ps-api/leaderboard` and `/temp-stats-data.json` on the same origin. Do not deploy these files over the live website without explicit review.

Next: create an installable website/API service with read-only DB credentials, authentication-independent API endpoints, pagination, rate limiting, response caching, country flags, and a configurable DB target. The website should work against the validated D3 scratch database for development and a dedicated read-only account for production.
