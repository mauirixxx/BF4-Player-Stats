# Battlefield Agency / BF4DB integration (Alembic 0027)

- `soldier_ban_status` is an optional per-soldier cache. NULL or absent row means unknown. BA and BF4DB are independent.
- `website/api/ban_status.py` is read-only and the dossier requests `/bf4ps-api/ban-status?soldier_id=<id>`; the endpoint checks the exclusion filter and returns unknown for non-PC.
- `website/scripts/refresh_ban_status.py --persona-id <id>` is an explicit one-persona verifier. Use `--dry-run` before enabling writes. It requires `BF4PS_DATABASE_URL`, writes only matching PC soldiers, and retains previously verified provider status when that provider fails.
- Keep the public web DB role SELECT-only. Use a separate restricted write role for the refresh script. No automatic per-view outbound requests.
- BA's historic ban state can be NULL on a confirmed ban. Explicit unknown states are not treated as clean. Lifted states are not active bans. A missing or incomplete ban-list page never establishes clean status.
- BA `/api/ban/` returns player UUIDs but not necessarily BF4 persona IDs; do not claim a bulk import is complete without an authoritative identity mapping. A bulk importer and rate-limited scheduler are future work.
- The migration creates no cache rows. Verify a known-positive PC soldier (persona 941293200, soldier 11711473) after deploying the read endpoint and writing a verified status.

## Bounded production backfill (2026-11-23)

- Agency importer: `website/scripts/import_agency_bans.py`. Fetches `/api/ban/?page=N&size=100`, resolves each Agency UUID through `/api/player/{id_}`, and matches **only** BF4 `personae[].persona_id` to existing PC soldiers. Writes only explicit active bans; no list absence is treated as clean. Defaults to dry-run. `--apply` requires PostgreSQL peer access on `bf4ps-db`. Use `--start-page`, `--pages` (max 100), `--size` (max 100), and `--delay` (min 0.5s) for bounded runs. No timer is installed.
- BF4DB queue: `website/scripts/verify_bf4db_queue.py`. Only checks existing cached Agency UUIDs with missing or older-than-seven-day BF4DB checks. Defaults to dry-run; `--apply` persists independent BF4DB results. API errors or missing explicit booleans never become clean. Use `--limit` (max 500) and `--delay` (min 0.5s). No timer is installed.
- Initial production pilot: 10 Agency bans imported, 10 persona identities resolved, 10 matches; BF4DB attempted 10 and verified 9, one unresolved. Including preexisting Not-ByK, 11 cached BA bans and 10 verified BF4DB statuses. The Agency list reported 61,887 ban records at pilot time; this is not a count of unique BF4 PC personas. A complete import requires paginated continuation, checkpointing, deduplication across pages, and rate-limit/429 handling before enabling unattended operation.
- **Do not run full historical backfill unattended yet.** The bounded scripts are manual pilots; they do not have durable retry/checkpoint state or a dedicated restricted write role. Do not give the public web API write access to this table.
