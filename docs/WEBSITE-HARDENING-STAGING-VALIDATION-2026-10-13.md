# BF4PS Website Hardening — Staging Validation

Date: 2026-10-13
Status: **Maintenance, API-outage detection/recovery, and DB-failure detection validated; DB recovery pending**
Branch: `feature/website-hardening`
Environment: `tcou`; BF4PS D3 scratch database (`bf4ps_scratch_stage9c_d3`), not production BF4SW.

## Verified

- Both Python modules `api/leaderboard_api.py` and `api/temp_dashboard_export.py` compiled successfully.
- Normal staging API `GET /health` on port 8766 returned HTTP 200 and `{"status":"ok"}`.
- With `MAINTENANCE_MODE=true`, staging `GET /health` and a leaderboard request returned HTTP 503, `Retry-After: 30`, and maintenance JSON.
- Switching maintenance off restored the staging health endpoint to HTTP 200 without restarting the API.
- The isolated frontend test server on 127.0.0.1:8877 returned HTTP 200 for `/`, `/bf4ps-api/health`, and `/temp-stats-data.json` in normal mode; proxied health returned HTTP 503 during maintenance.
- Operator verified in Firefox over SSH forwarding that the full-screen maintenance page rendered correctly, that switching maintenance on displayed it, and that switching maintenance off restored the normal website. Screenshot was shared in the validation conversation.
- Production API on 127.0.0.1:8765 and both BF4PS systemd services were confirmed active before browser testing. No Apache changes or live service restarts were needed for these tests.

## Boundaries and pending checks

- This is staging validation, **not production rollout approval**.
- No PostgreSQL service was stopped; production BF4SW database must remain untouched.
- **PASSED:** Stopping only the staging API on port 8766 triggered the maintenance view; restarting it restored the leaderboard automatically without a browser refresh. Operator reported recovery faster than the 15-second polling interval.
- **PASSED (failure detection):** Starting only the staging API with `BF4PS_DATABASE_URL` pointing at `127.0.0.1:1` caused a connection-refused error. Proxied `/bf4ps-api/health` returned HTTP 503 with `status: unavailable`, and Firefox displayed the maintenance view. Live BF4PS services remained active; live port 8765 `/health` returned expected HTTP 404 because its running version lacks that route.
- **PENDING:** Restore staging API to the valid D3 connection and verify automatic frontend recovery after simulated DB failure. No PostgreSQL instance was stopped or reconfigured.
- Verify frontend reload behavior and any initial flash before rollout.
- Confirm `MAINTENANCE_MODE=false`, stop temporary ports 8766/8877 after testing, and verify live services remain active.
- Prior to deployment, back up the deployed static HTML, document rollback, then deploy/restart only the BF4PS API as needed.

## Promotion gate

Do not merge into `WEBSITE` until failure-injection and recovery checks pass and operator approves deployment.
