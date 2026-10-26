# Platoon read API cutover — 2026-10-25

## Production architecture

The platoon website reads PostgreSQL through the existing BF4PS read API on tcou, proxied as `/bf4ps-api/`. It no longer downloads or parses the monolithic `platoons-data.json` snapshot.

- `GET /bf4ps-api/platoons?page=1&search=&sort=name&direction=asc`: server-side filtered, sorted, 50-row list and total count. Sort supports `name`, `members`, `created`; direction `asc` or `desc`.
- `GET /bf4ps-api/platoon-detail?id=<platoon_id>`: official Battlelog account roster, supported personas, lifetime soldier statistics, cached emblem URL, metadata.
- `GET /bf4ps-api/soldier-platoons?persona_id=<id>&platform=pc|ps4|xboxone`: roster associations and latest observed active platoon for soldier dossier.

SQL is SELECT-only, uses bound parameters, an 8-second statement timeout, and reads `platoons`, `platoon_roster_accounts`, `platoon_roster_personas`, `soldiers`, `detailed_stats_current`, and `platoon_soldier_discovery`. Identity association is still Battlelog account-roster association, not independently verified soldier membership. PS3/Xbox 360 are not displayed.

## Deployment and checks

Deploy `website/api/platoon_read_api.py` beside `leaderboard_api.py`, deploy the updated API handler, and restart `bf4ps-leaderboard-api.service`. Deploy `website/site/platoons-live.js`, `platoons.html`, `platoon-combat.js`, and `platoon-dossier.js` to the webroot. The admin overview reads PostgreSQL rather than the old snapshot.

Smoke test listing, filtered search, sort, individual platoon detail, soldier associations, and the admin overview. Verify browser roster expansion, combat ranking, back navigation, and deep links. Confirm no production source refers to `platoons-data.json` before removing the snapshot.

The obsolete `bf4ps-platoon-export.timer` is disabled. Do not reenable the timer or the old exporter. Retain local emblem PNG caching, which is separate from the obsolete JSON snapshot.

## Motivation and observed performance

The old snapshot was 89 MB and the exporter repeatedly timed out at 45 seconds, leaving tens of gigabytes of orphaned temporary JSON files. The new 50-row first-page response measured about 16 KB and ~40 ms on the local API. Production HTTPS smoke tests returned HTTP 200 for search, member sort, platoon detail, and soldier associations.

No gameplay/statistics fields are intentionally removed; retrieval is now scoped to the selected platoon or page. Schema and query changes must be checked against `docs/database-schema.md` and `docs/operational-schema.md` and the live schema.
