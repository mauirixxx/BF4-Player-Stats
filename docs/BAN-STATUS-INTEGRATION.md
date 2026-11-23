# Battlefield Agency / BF4DB integration (Alembic 0027)

- `soldier_ban_status` is an optional per-soldier cache. NULL or absent row means unknown. BA and BF4DB are independent.
- `website/api/ban_status.py` is read-only and the dossier requests `/bf4ps-api/ban-status?soldier_id=<id>`; the endpoint checks the exclusion filter and returns unknown for non-PC.
- `website/scripts/refresh_ban_status.py --persona-id <id>` is an explicit one-persona verifier. Use `--dry-run` before enabling writes. It requires `BF4PS_DATABASE_URL`, writes only matching PC soldiers, and retains previously verified provider status when that provider fails.
- Keep the public web DB role SELECT-only. Use a separate restricted write role for the refresh script. No automatic per-view outbound requests.
- BA's historic ban state can be NULL on a confirmed ban. Explicit unknown states are not treated as clean. Lifted states are not active bans. A missing or incomplete ban-list page never establishes clean status.
- BA `/api/ban/` returns player UUIDs but not necessarily BF4 persona IDs; do not claim a bulk import is complete without an authoritative identity mapping. A bulk importer and rate-limited scheduler are future work.
- The migration creates no cache rows. Verify a known-positive PC soldier (persona 941293200, soldier 11711473) after deploying the read endpoint and writing a verified status.
