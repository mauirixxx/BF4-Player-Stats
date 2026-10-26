> Historical checkpoint. Current production retrieval architecture: [PLATOON-READ-API-CUTOVER-20261025.md](PLATOON-READ-API-CUTOVER-20261025.md).

# Platoon production checkpoint — 2026-10-18

Production nodes: `mak-05` (platoon collector), `tcou` (site/API), `mak-db-02` (PostgreSQL primary). The repo contains source code, **not** production DB contents, secrets, generated `platoons-data.json`, saved Battlelog HTML, or cached PNG emblems.

## Deployed functionality

- Alternating 15-second platoon-roster/soldier-inspection scheduling on `mak-05`, using the existing queue and pacing. Active platoon extracted from the soldier's `span.club-link`; unrelated links do not count.
- Official Battlelog platoon metadata: name, tag, roster, roles, creation date, emblem path (`club.emblemPath`), and website (`club.webSite`). The last two use additive PostgreSQL columns.
- Historical 2026-10-18 export (retired 2026-10-25): read-only database joins for official accounts, supported PC/PS4/Xbox One personas, soldier detailed stats, active platoon links, and cached emblem URLs. PS3/Xbox 360 remain in PostgreSQL but are hidden from the public roster. Counts use the filtered roster.
- Public platoon directory: search, sortable members/creation date, 50-row pagination, emblems and dossier routing.
- Dossier: emblem left, six lifetime-roster aggregate stats in a 3-by-2 grid right, sortable/searchable soldier leaderboard below, collapsible official Battlelog roster, and website link. Aggregate K/D = sum kills / sum deaths; KPM = sum kills / sum playtime minutes; only soldiers with detailed stats are counted. Statistics coverage displays tracked / eligible soldiers. Figures are **not** platoon-only gameplay totals.
- Soldier dossier: known platoon badges and active link, manual **Refresh Platoon** button backed by a CSRF-protected gateway and priority `platoon_soldier_discovery` queue request. The button confirms queue submission; users must reload for finished results.

## Deployment requirements

1. Apply `docs/PLATOON-20261018-PRODUCTION-ADDITIONS.sql` to `bf4_playerstats` before deploying the collector or exporter.
2. Deploy `scripts/battlelog_platoon_roster.py`, `scripts/import_platoon_rosters.py`, `scripts/platoon_alternating_scheduler.py` and related worker scripts to `mak-05`. Existing systemd alternating timer/service must be configured separately; no automatic installation is provided by this checkpoint.
3. Deploy `scripts/platoon_submit_api.py` to `tcou` under the submission service. Deploy `website/api/platoon_read_api.py` and the read API handler; do not deploy the retired JSON exporter. Deploy `site/platoons.html`, `site/platoons-live.js`, `site/platoon-combat.js`, `site/platoon-dossier.js`, `site/platoon-gateway.php`, `site/platoon-refresh-gateway.php`, and `site/soldier.html` into the site webroot.
4. Configure `/var/lib/bf4ps-platoon-refresh-limits` writable by `www-data`, and retain existing CSRF/origin and trusted-LAN controls. Never commit production environment files.
5. Verify `node --check` on JS files, `php -l` on PHP gateways, `python3 -m py_compile` on scripts, and API endpoint success. Check the dossier at `/platoons.html?id=8007224580313493523` (website test) and `/platoons.html?id=6011332291485901135` (stats test).

## Outstanding

- Automatic rescheduling of completed soldier inspections has not been implemented; manual Refresh Platoon queues another inspection.
- Source code checkpoint does not include deployment automation, a complete schema migration history, or any runtime credentials.
