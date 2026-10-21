# BF4 Player Stats — Website release (2026-10-15)

This release packages the **deployed website and manual-request integration**. It is not a collector-fleet image or an all-in-one installation. The distributed collector, dispatcher, PostgreSQL migrations 0001–0012, and scheduler remain separate components.

## Production architecture

- Public website: Apache/PHP on `tcou`, `/var/www/bf4playerstats.com`; tracked deployment source in `site/`.
- Read-only leaderboard API: `api/leaderboard_api.py`, localhost port 8765, served publicly under `/bf4ps-api/`.
- Private manual API: `api/manual_request_api.py`, localhost port 8789, systemd unit `deploy/systemd/bf4ps-manual-api.service`.
- Public manual gateway: `site/manual-gateway.php`. PHP session CSRF, strict origin/host checks, a private server-side token, and per-client-IP rate limiting. Never expose the token to JavaScript.
- Database: PostgreSQL `bf4_playerstats` via HA DNS name `db.bf4statusbot.com`. The private API uses dedicated least-privilege role `bf4ps_manual_api`, which executes SECURITY DEFINER functions; no direct write access to collector tables.
- Snapshot exporter: `api/temp_dashboard_export.py` writes generated `temp-stats-data.json` to the web root; **never commit that generated file**.

## Features

- Search soldiers by current name or persona ID; asynchronous alias search resolves historical names from `soldier_names` to the **same soldier_id**. A soldier is unique by `(platform, persona_id)`, not by name.
- Soldier dossier displays up to eight known names initially, with an expandable list and first/last-seen timestamps.
- Add Stats accepts a valid Battlelog soldier URL, records the submitted name as an alias, and schedules the existing four resource jobs without a separate verification request. Existing names do not overwrite an existing soldier's authoritative current name.
- Refresh Stats prioritizes existing soldier collection jobs subject to the DB cooldown and the fleet's global pacing/manual-share rules.
- Public website has Open Graph and Twitter large-card metadata; `site/og-preview.png` is the 1200×630 preview image.
- Interactive API calls do **not** bypass global Battlelog request budgeting.

## Deployment checklist

1. **Back up the live web root and configuration**; check out the release tag into a separate staging directory, never overwrite a running checkout blindly.
2. Compare production configuration against `deploy/apache/`, `deploy/systemd/`, and the existing Apache proxy mapping. The checked-in Apache file is a historical deny-only example, **not** the active public PHP gateway.
3. Confirm PostgreSQL schema version `0012_manual_verify_api` and required roles/functions. The production SQL for the direct-add function is preserved at `deploy/sql/manual-direct-add.sql`. It has already been applied in production; **do not apply blindly to a different schema**. This SQL is a supplemental, idempotent function definition, not a numbered Alembic migration.
4. Provision environment variables and private token **outside the web root**. Do not commit `/etc/bf4ps-website/manual-api.env` or `/root/.config/bf4ps/website-production.env`.
5. Deploy reviewed `site/` files to the Apache document root, preserving local runtime-generated data, equipment assets, flags, and maintenance state. Do not copy `.git`, `.venv`, or backups.
6. Install dependencies and services according to existing host configuration; verify localhost binding for ports 8765 and 8789, PHP/cURL, HTTPS, Apache trusted proxy real-IP setup, and writable `/var/lib/bf4ps-manual/limits/`.
7. Validate public `/index.html`, `/soldier.html`, `/og-preview.png`, `/bf4ps-api/alias-search?q=yellowh00d`, `/bf4ps-api/aliases?soldier_id=1930`, and the CSRF GET flow at `/manual-gateway.php`. Do **not** use a production POST as a deployment smoke test without operator approval.

## Limits, caveats and follow-up

- Public IP rate limit: **10 submissions per rolling hour per IP**; configured LAN CIDRs bypass the PHP limiter.
- The authenticated private API still has a **10/minute localhost in-memory limiter**, which can constrain bursts even for LAN-exempt clients. This is a known follow-up; do not claim unlimited LAN throughput.
- Alias lookup is a separate read-only API request. The global homepage search uses its results to augment the existing snapshot search; a delayed response may update matches after the initial current-name matches.
- Soldier dossier and leaderboards use a generated snapshot. A newly admitted soldier appears once the exporter refreshes and relevant collection succeeds.
- SQL in `deploy/sql/manual-direct-add.sql` must be folded into an Alembic migration before a future full collector release.
- The collector code and production schema documentation live on a different development branch; do not merge/rebase them into this website release without a dedicated integration review.
- No secrets, database dumps, generated player data, local Python environments, or timestamped backups belong in this release.

## Validation recorded on 2026-10-15

- `/bf4ps-api/alias-search?q=yellowh00d` returned HTTP 200 and resolved to soldier ID 1930.
- `/bf4ps-api/aliases?soldier_id=1930` returned HTTP 200 with alias timestamps.
- Public `/index.html` exposes `og:title`; public `/og-preview.png` returned HTTP 200; Discord rendered the rich preview.
- User confirmed Add Stats inserted FooeY and the site displayed the soldier.
