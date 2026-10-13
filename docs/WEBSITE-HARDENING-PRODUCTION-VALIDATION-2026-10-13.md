# Website hardening — production validation (2026-10-13)

## Outcome
**Operator-confirmed successful deployment and live maintenance-mode validation** on `tcou` for bf4playerstats.com.

## Source and deployment
- GitHub PR #2 merged into `WEBSITE` as commit `dce3db51965251b13539f07f244cb8717fe62522`.
- Deployed frontend `site/index.html` matched `/var/www/bf4playerstats.com/index.html` with SHA-256 `00dc2c52a9327e1d58aef87dbf9def8471aef29525543e40865ed81a65b6c275`.
- Frontend backup retained at `/var/www/bf4playerstats.com/index.html.backup-20261013-132138`.
- Restarted only `bf4ps-leaderboard-api.service`. The first immediate curl attempt briefly failed during startup; subsequent `127.0.0.1:8765/health` returned HTTP 200 `{"status": "ok"}`.
- HTTPS virtual-host proxy verified with `curl --resolve bf4playerstats.com:443:127.0.0.1 https://bf4playerstats.com/bf4ps-api/health`, returning HTTP 200 `{"status": "ok"}`. The earlier 127.0.0.1 HTTP port 80 request returned 404 because it selected a different virtual host.
- Operator confirmed the normal leaderboard rendered in Firefox after deployment.

## Live maintenance-mode validation
- Operator confirmed the final live maintenance-mode test passed, including activation, maintenance-page display, disabling maintenance, and automatic return to normal leaderboard.
- The operator did not paste the final maintenance/recovery HTTP traces; this section records operator confirmation, not independently captured response headers.
- Intended final setting: `MAINTENANCE_MODE=false`. A post-test file read was not supplied.
- No Apache configuration changes, PostgreSQL shutdowns, BF4SW service changes, or database migrations were part of this rollout.

## Follow-up
- Confirm `MAINTENANCE_MODE=false` and both BF4PS systemd services remain active in the next routine check.
- Keep the original frontend backup until a later cleanup decision.
- Continue future work from the documented design and verify the live DB schema before writing new database queries.
