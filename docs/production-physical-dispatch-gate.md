# Production physical-dispatch ceiling — implementation gate

Status: **HOLD — not approved for undrain**. Baseline: `fix/rnt-01-safe-collector-bootstrap` at `17727d8`.

## Requirement
Across **all production BF4PS collector workers and egress keys**, authorize no more than **1,296 physical outbound HTTP attempts in any rolling 3,600-second interval**. Each network attempt consumes a unit even if it times out, returns HTTP error, or its persistence fails. Per-egress pacing remains separately enforced.

## Current implementation findings
- `bf4ps/background_service.py` enforces a rolling count of **collection attempts** plus claimed/running reservations, not a count of actual HTTP attempts.
- `bf4ps/request_gate.py` serializes **per-egress** request times only; it has no fleet-wide hourly capacity check.
- `bf4ps/profile_collector.py` can call `fetch_account_username` and then `fetch_profile` within a single collection job, with only one `collection_attempt_started` event. This can cost two physical HTTP attempts.
- Current code records collection-attempt evidence before HTTP for other resources, but this does not itself prove a shared fleet-wide physical limit.

## Design contract before implementation
1. Consult the documented PostgreSQL schema and compare it to the live schema **read-only** before choosing a ledger/table or migration. Do not infer columns or constraints.
2. Reserve a durable, unique physical-dispatch token **transactionally under a PostgreSQL cluster-wide lock** before each network attempt. Enforce the rolling window at reservation time, including reservations for requests that may not reach the network (conservative charging).
3. Count across all resources, retry paths, collector identities, and egress keys. The physical gate must be independent of background-job fairness admission; keep the existing fairness logic and per-egress spacing.
4. Fail closed if the budget ledger, transaction, database, or authorization fails. Do not issue HTTP without a committed token.
5. Count redirects and any implicit client retries, or disable them and require each follow-up attempt to obtain its own token. In particular, `urllib.request.urlopen` may follow redirects; inspect each call site.
6. Cover the soldier-account resolution and profile fetch separately. Preserve lease checks and durable diagnostic events.
7. Preserve discovery behavior; do not apply a collector gate to discovery without an explicit scope/design decision.
8. No activation until tests prove: 1,296 permitted / 1,297th denied; rolling-window expiry; multi-worker contention; retries/errors; profile two-request case; redirects; DB failure; all collector resources; no production DB writes in tests.
9. Inspect Stage 9C test evidence and document what it did and did not prove. Do not rerun the 450/1,800 cohort tests simply to verify this gate.

## Rollout
- Commit implementation and focused tests on this fix branch.
- Run static/focused tests against an isolated database, not production.
- Deploy collector-only image to rnt-01 while **drained**; verify heartbeat and registration.
- Approve the production physical-dispatch ceiling only after all checks pass; undrain explicitly as a separate operator action.

No changes in this document authorize collector resume.
