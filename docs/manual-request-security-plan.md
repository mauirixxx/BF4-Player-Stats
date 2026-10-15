# Manual Battlelog submissions: security and rollout plan

Status: design checkpoint, backend scaffold only; public buttons remain disabled.

## Boundaries

- `bf4ps_stage9c_d2` remains read-only and powers the leaderboard.
- A **new, dedicated login role** will be created only when the API and stored
  functions have been independently reviewed and tested. No credentials in Git.
- The login role must have no direct INSERT/UPDATE/DELETE on `soldiers`,
  `collection_jobs`, `collection_state`, or any stats tables. Revoke PUBLIC
  EXECUTE on privileged functions and grant only named function signatures.
- Stored functions use fixed SQL, fixed `search_path`, schema-qualified objects,
  and a non-login owner with only the required table privileges. Reject arbitrary
  user-provided SQL and do not accept a caller-provided priority value.
- The public HTTP API is separate from the read-only leaderboard endpoint;
  validate URLs, request body size, IP rate limits, and CSRF/origin behavior.
  Never expose the database credentials or direct PostgreSQL port to browsers.

## Request semantics

1. Validate an HTTPS Battlelog BF4 soldier stats URL offline. This establishes
   claimed platform/persona/name, **not** proof the remote soldier exists.
2. Resolve Battlelog identity safely through the existing collector pipeline;
   do not treat unverified submitted names as authoritative identity.
3. Serialize requests by soldier and atomically enforce the 60-minute request
   cooldown. Return existing request status for duplicate pending work.
4. Enqueue missing/stale resources in the **background execution lane** using
   a bounded interactive priority; do not alter claimed/running job leases or
   existing retry backoff. Profile is included alongside the three stats types.
5. Preserve background fairness and the 5-second per-egress request gate plus
   physical/background fleet budgets. The existing background admission policy
   must be explicitly modified and tested before priority activation.
6. Display queued/running/completed/retrying using actual collection state and
   collection event evidence. Request acceptance is not collection success.

## Staged activation

- Stage A: isolated migration tests and schema audit (no production writes).
- Stage B: restricted SQL functions and role on disposable test database;
  concurrency, cooldown, idempotence, lease and authorization tests.
- Stage C: API, abuse controls, and request status; exercise against test DB.
- Stage D: controlled production migration and private smoke test.
- Stage E: enable Add Stats and Refresh Stats publicly; monitor priority share,
  collection failures, egress dispatch and fleet-wide backlog throughput.

Rollback must disable the API and new admission first. Never drop populated
manual request ledgers as part of a routine downgrade.