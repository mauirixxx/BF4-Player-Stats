# Manual request API: PostgreSQL least-privilege contract

Status: design and authorization checkpoint. **Do not create a login or expose an endpoint yet.**

## Identity and privilege separation

- `bf4ps_stage9c_d2` stays read-only; never repurpose its password or grants.
- Future `bf4ps_manual_api` LOGIN gets `CONNECT` on the selected database, `USAGE` on a dedicated `manual_api` schema and `EXECUTE` only on explicitly listed function signatures. No table access, no schema CREATE, no role membership, no BYPASSRLS, no superuser or CREATEDB.
- A separate NOLOGIN function owner (`bf4ps_manual_function_owner`) owns narrowly scoped SECURITY DEFINER functions. Grant it only required SELECT/INSERT/UPDATE on soldiers identity, collection_state freshness, collection_jobs pending rows, manual request ledger and cooldowns. Never grant DELETE or stats-table writes.
- SECURITY DEFINER functions must set `search_path = pg_catalog, pg_temp` and schema-qualify every table, sequence, and helper. Revoke EXECUTE from PUBLIC in the same transaction that creates each function. Never interpolate user-controlled SQL identifiers.
- Database ownership and Alembic migration privileges stay separate from the public API role. No passwords, hashes or connection strings in Git.

## Request contract

`manual_api.request_existing_soldier(persona_id bigint, platform text, kind text)` returns `request_id`, `state`, `retry_after_seconds`, and work counts. Inputs are validated in the API *and* SQL function. The API parses the Battlelog URL but never trusts its displayed soldier name. The SQL function must perform the authoritative identity lookup, soldier-row lock, cooldown check, freshness check, and lease-safe queue changes atomically.

The SQL function must not accept a priority, lane, eligible timestamp, retry count, lease token, arbitrary SQL, or a caller-selected soldier_id. Unknown soldiers must return `not_registered` without inserting a synthetic identity. Add Stats for new identities is a separate verified-ingestion workflow; it is **not** enabled by this existing-soldier function.

When all resources are fresh, return `up_to_date` without consuming a new cooldown. For resources with an existing running/leased or backed-off job, report that work as pending without changing its lease or backoff. Never advertise completed collection merely because admission succeeded.

## Deployment gates

1. Test function against an isolated scratch DB; run concurrent duplicate requests, grants/denials, lease preservation, and cooldown tests.
2. Explicitly drop scratch DB and temporary pg_hba rule after test, and verify both are gone.
3. Provision login secret outside Git, restricted to the API host, only after security review.
4. Enable private HTTP endpoint with body size limits, IP throttling, origin restrictions, and clear error/status handling.
5. Migrate production only after rollback path is verified; enable public controls last.