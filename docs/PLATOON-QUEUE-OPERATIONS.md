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
