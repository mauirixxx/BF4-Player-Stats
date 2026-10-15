# BF4 Player Stats — Website

Production website source for **[bf4playerstats.com](https://www.bf4playerstats.com/index.html)**. This repository also contains the BF4PS distributed collector on other branches; this release line is scoped to the website, read-only leaderboard API, manual-request gateway, and their deployment artifacts.

## Features

- Cross-platform BF4 soldier lookup, leaderboards, equipment views, and individual dossiers.
- Historical-name search and expandable alias lists, keyed to the same soldier by platform and persona ID.
- Add Stats and Refresh Stats requests through a hardened PHP gateway and localhost-only private API.
- Discord/social Open Graph previews via `site/og-preview.png`.
- Existing distributed collectors continue to own scheduling, Battlelog requests, retries, and database persistence.

## Files

- `site/`: public Apache document root (excluding generated runtime data).
- `api/leaderboard_api.py`: read-only leaderboard and alias endpoints.
- `api/manual_request_api.py`: private authenticated manual-request backend.
- `api/temp_dashboard_export.py`: generated website snapshot exporter.
- `deploy/`: example Apache/systemd configuration and supplemental direct-add SQL.
- `docs/RELEASE-WEBSITE-2026-10-15.md`: authoritative deployment checklist, limitations, security model, and validation.

**Deployment is not a blind directory copy.** Follow the release checklist and preserve existing production configuration and runtime-generated files. No credentials or player snapshot JSON are included.

## Validation

Run `python -m unittest discover -s tests`, `python -m py_compile api/*.py`, and `php -l site/manual-gateway.php` before deploying. Test against a staging copy first. Do not use production manual POST requests as unattended smoke tests.
