# Platoon admission and dynamic scheduling (deployed 2026-10-18)

## Production layout

- Public form: `site/shared-header.js`, on `/platoons.html`.
- CSRF / per-IP admission gateway: `site/platoon-gateway.php`; maximum five submissions per hour per remote address.
- Loopback admission service on tcou: `scripts/platoon_submit_api.py`, port 8792, systemd `bf4ps-platoon-submit.service`.
- Queue: `bf4_playerstats.public.platoon_requests`; idempotent `platoon_id` primary key, bounded retry count.
- Worker on mak-05: `scripts/platoon_queue_worker.py`, systemd `bf4ps-platoon-queue.timer` every 15 minutes; maximum one roster per invocation, file lock, HTTPS-only fixed Battlelog host, full parser validation, atomic SQL import.
- The earlier hardcoded daily `bf4ps-platoon-refresh.timer` was disabled, superseded by the dynamic timer. Existing platoons are due daily based on `platoons.next_refresh_at` or `last_success_at + 1 day`; queue admissions take priority. Failed known-platoon refreshes retry after two hours; new admissions retry with exponential delay up to eight attempts.
- Website snapshot exporter on tcou: `bf4ps-platoon-export.timer`, every 30 minutes.
- PostgreSQL hostname: `db.bf4statusbot.com`, not an individual physical DB IP.

## Verification

- Public submission of an existing Team Wired URL returned `already_collected`.
- A test queue entry for the existing UCAV Church platoon was consumed by the worker, which fetched, parsed and committed 37 accounts and 46 persona associations. Test queue entry deleted afterward.
- No unknown/new platoon has yet been used in a full end-to-end public admission test. Monitor first real admission before treating that path as proven.
- Observe worker: `journalctl -u bf4ps-platoon-queue.service -n 50 --no-pager` on mak-05.
- Observe admission: `journalctl -u bf4ps-platoon-submit.service -n 50 --no-pager` on tcou.
- Observe queue: `SELECT platoon_id,status,attempts,next_attempt_at,last_error FROM platoon_requests ORDER BY requested_at DESC;`.

## Database schema addition

```sql
CREATE TABLE platoon_requests (
  platoon_id bigint PRIMARY KEY CHECK(platoon_id>0),
  requested_at timestamptz NOT NULL DEFAULT now(),
  last_attempt_at timestamptz,
  next_attempt_at timestamptz NOT NULL DEFAULT now(),
  attempts integer NOT NULL DEFAULT 0,
  status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','running','complete','failed')),
  last_error text
);
```

Grants: `bf4ps_platoon_collector` SELECT/INSERT/UPDATE, `bf4ps_stage9c_d2` SELECT/INSERT on `platoon_requests`. Existing website role has SELECT on the four platoon roster tables. No grants to existing soldier statistics mutation tables were added.

## Soldier-page platoon discovery (2026-10-18)

- `platoon_soldier_discovery` tracks per-soldier status, retries, observed displayed tag, and the official linked platoon ID independently. Existing soldier statistics scheduling is untouched.
- `scripts/discover_soldier_platoons.py` seeds only supported PC/PS4/Xbox One soldiers currently evidenced in confirmed platoon rosters; no mass backfill of the broader soldier database.
- On mak-05, `bf4ps-platoon-discovery.timer` invokes `bf4ps-platoon-discovery.service` every 15 minutes, one soldier per run, using a filesystem lock and bounded retries. It fetches only the fixed Battlelog HTTPS host, parses official numeric `/bf4/platoons/view/<id>/` links, and deduplicates via `platoon_requests` and `platoons`.
- Displayed `[TAG]` and linked platoon ID are stored as distinct observations. A tag alone is never treated as evidence of a platoon ID or membership.
- First live tests: `mauirixxx` showed tag `[HOLY]` but linked UCAV Church (`4452867151931601735`); `IMIr_Grinch` yielded new ID `4705241243200910871`, queued for roster collection.
- This initial worker does not yet periodically recheck completed soldiers for changes in active platoons. That can be added later with a slow TTL.
- Monitor: `journalctl -u bf4ps-platoon-discovery.service -n 40 --no-pager` and `SELECT status,count(*) FROM platoon_soldier_discovery GROUP BY status;`.

Schema:
```sql
CREATE TABLE platoon_soldier_discovery (
 soldier_id bigint PRIMARY KEY REFERENCES soldiers(soldier_id),
 status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','running','complete','failed')),
 attempts integer NOT NULL DEFAULT 0,
 next_attempt_at timestamptz NOT NULL DEFAULT now(),
 last_checked_at timestamptz,
 linked_platoon_id bigint,
 displayed_tag text,
 last_error text,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_platoon_soldier_discovery_due ON platoon_soldier_discovery(next_attempt_at) WHERE status IN ('pending','failed');
```

## Production platoon artwork reconciliation (2026-10-27)

Battlelog `platoons.emblem_path` is the authoritative URL template, not the cached file. The public read API (`website/api/platoon_read_api.py`) intentionally **never fetches external URLs** on requests: it displays `/assets/platoon-emblems/<platoon_id>-<sha256(url)[:16]>.png` when present, otherwise the default emblem. A newly imported platoon can therefore show the fallback until the background cache job runs.

On `tcou`, deploy `website/scripts/cache_platoon_emblems.py` to `/opt/bf4ps-website/scripts/`, install `website/deploy/bf4ps-platoon-emblem-cache.{service,timer}` into `/etc/systemd/system/`, run `systemctl daemon-reload`, and `systemctl enable --now bf4ps-platoon-emblem-cache.timer`. Check with `systemctl status bf4ps-platoon-emblem-cache.timer` and `journalctl -u bf4ps-platoon-emblem-cache.service`. Manual safe test: `set -a; . /root/.config/bf4ps/website-production.env; set +a; /opt/bf4ps-website/.venv/bin/python /opt/bf4ps-website/scripts/cache_platoon_emblems.py --dry-run --limit 5` (avoid printing environment variables). The job is read-only against PostgreSQL and writes only validated PNG files to the website cache. Every run fetches at most 20 missing emblems, with a 6-hour per-file failure cooldown. It accepts only Battlelog's fixed HTTPS Akamai emblem host/path, rejects redirects, caps responses at 1 MB, and publishes files atomically. New platoons appear after their metadata has been collected and a cache cycle completes. The cached filename includes a hash of the resolved URL, so changed Battlelog emblems are fetched as new assets.

Platoon admission API: production `bf4ps-platoon-submit.service` uses `website/api/platoon_submit_api.py` at `/opt/bf4ps-website/api/platoon_submit_api.py`, **not** `/tmp`. Deploy the matching service unit from `website/deploy/bf4ps-platoon-submit.service`; it binds loopback `127.0.0.1:8792` and requires the existing private gateway security checks. `systemctl restart bf4ps-platoon-submit.service` and verify its listener. Keep database credentials in the existing root-only environment file; never commit them.

## Discord platoon unfurl previews (2026-10-27 regression repair)

`website/site/share-preview.php` is used by Apache's existing `.htaccess` rewrite for `platoons.html?id=<id>`. It reads `platoon-preview-index.json` and renders server-side OG/Twitter metadata. The former index generator read `platoons-data.json`, which no longer exists after the switch to live paginated platoon API; its systemd service failed, leaving stale/missing names for newly collected platoons. The replacement `website/scripts/build_platoon_preview_index.py` reads the authoritative `platoons` table directly with a read-only SQL transaction, then atomically publishes a small JSON index every five minutes via `bf4ps-share-preview-index.timer`. It never runs large roster/stat queries.

When an official Battlelog emblem has been cached **and its v3 wide card generated**, the preview uses `/assets/platoon-previews/<platoon_id>-<urlhash>-v3.png`; otherwise it retains the existing 1200x630 standard `og-preview.png`. The PHP code accepts only a deterministic local emblem path and verifies the file exists. Deploy the PHP file to `/var/www/bf4playerstats.com/share-preview.php`, Python scripts to `/opt/bf4ps-website/scripts/`, and the matching systemd service/timer from `website/deploy/`; restart the index service after artwork cache cycles to refresh newly cached paths. Test with `curl -s 'https://bf4playerstats.com/platoons.html?id=<id>' | grep -E 'og:title|og:image'`; test both www and bare domains and both a cached and default emblem. Discord caches link unfurls; add a harmless query parameter when retesting.

### Wide Discord platoon artwork (2026-10-27)

Square Battlelog emblems render with excess vertical whitespace in Discord large-image embeds. `website/scripts/build_platoon_preview_images.py` produces 1200x630 branded cards from the already-cached local emblem PNGs (never fetching remote assets). It preserves the emblem aspect ratio and alpha channel on a dark BF4PS background, writing atomically to `/assets/platoon-previews/<platoon_id>-<urlhash>-v3.png` (current production format). The `bf4ps-platoon-preview-images.timer` processes up to 50 new images per five-minute cycle. The preview-index builder selects a generated wide card only if its file exists; otherwise `share-preview.php` uses the existing standard `og-preview.png`. This leaves original artwork untouched on the platoon page. To deploy, install the new image script in `/opt/bf4ps-website/scripts/`, the matching service and timer under `/etc/systemd/system/`, update `build_platoon_preview_index.py` and `share-preview.php`, then run `systemctl daemon-reload; systemctl enable --now bf4ps-platoon-preview-images.timer`. Trigger `systemctl start bf4ps-platoon-preview-images.service` followed by `systemctl start bf4ps-share-preview-index.service` for immediate updates. Discord may cache old image metadata: use a unique query parameter for validation.

### Historical preview card layout revision v2 (superseded; 2026-10-27)

The emblem area was enlarged to 495x495 maximum within the 1200x630 card, and the left panel expanded. Generated preview filenames now end in `-v2.png` to invalidate Discord/CDN image caches without overwriting the original `-<hash>.png` cards. The index publishes a v2 URL only after its generated file exists; otherwise the generic OG card remains the fallback. Regenerate with `systemctl start bf4ps-platoon-preview-images.service`, then rebuild the index. Older v1 files can be removed after v2 backfill if no longer referenced.

### Current production preview card layout v3 (approved; 2026-10-27)

Fixed a Pillow scaling bug: `thumbnail()` never enlarges a 256x256 Battlelog emblem, even when the design reserves 495x495. The renderer now calculates a proportional scale factor and uses `resize(..., Image.Resampling.LANCZOS)` to upscale smaller emblems into the available 495x495 panel, preserving transparency and aspect ratio. The output filename suffix is `-v3.png` to invalidate Discord/CDN caches. Existing v2 images remain intact until no longer referenced.

**Production acceptance:** Discord preview confirmed with IMMORTALS (`6332892298735728097`): enlarged lion emblem fills the left panel; the card remains 1200x630 and the right-side branding remains legible. v3 is the permanent default for all cached Battlelog platoon emblems. The generator and index timers are enabled on `tcou`. To confirm deployed state, check `systemctl is-enabled bf4ps-platoon-preview-images.timer`, `systemctl is-active bf4ps-platoon-preview-images.timer`, and `curl -s "https://bf4playerstats.com/platoons.html?id=6332892298735728097" | grep -E "og:title|og:image"`. Avoid using the superseded v1/v2 card URLs in new integrations.

### Legacy Battlelog HTTP emblem URLs (2026-10-27)

Some official Battlelog platoons (e.g. Reign of Fire, `7828868782093312288`) retain `http://eaassets-a.akamaihd.net/...` in `platoons.emblem_path`. The emblem reconciler now upgrades **only this exact allowlisted host** from HTTP to HTTPS before validation, hashing, and fetching. All downloads remain HTTPS, with the existing strict emblem-path validation, redirect rejection, and response-size cap. This is compatible with existing cached filenames derived from the HTTPS URL. Do not relax the host allowlist or permit arbitrary HTTP fetches.
