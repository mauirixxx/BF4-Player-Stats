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

## Stage 9C migration discovery (2026-10-13)
- Migration `0005_stage9c_dispatch_ledger` **already defines** `outbound_dispatches`: `dispatch_id`, `job_id`, `attempt_number`, `resource`, `lease_token`, `collector_uuid`, `egress_key`, `lane`, `payload_fingerprint`, `admitted_at`, `phase`, `send_marked_at`, `acknowledged_at`. Its docstring explicitly states admission and actual-send guarantee are unimplemented.
- The unique constraint `uq_outbound_dispatch_identity` on `(job_id, attempt_number, resource, lease_token)` prevents using two rows for two physical HTTP calls in one profile attempt. A compatible additive schema change is needed if this ledger is reused; preserve historical records and do not rewrite prior evidence.
- Migration `0006_stage9c_soak_round_ledger` is explicitly marked scratch-only. Do **not** infer from the revision number that production migrations or tables may be modified. Read-only inspect the production schema and migration state before deciding the safe production migration path.
- Existing `outbound_dispatches` index `ix_outbound_dispatch_background_admitted` is background-scoped. A fleet-wide physical gate must count every production collector lane and egress, not just background.
- `bf4ps/profile_collector.py` makes the account-resolution request before its `collection_attempt_started` event; therefore event-based accounting is not sufficient.
- Next: reconcile the Stage 9C ledger semantics and migration constraints with actual production DDL, then implement physical reservations, send markers, redirect policy, and isolated tests. No undrain authorized.

## Production read-only schema verification (operator output, 2026-10-14 UTC)
- `alembic_version.version_num = 0006_stage9c_soak_round_ledger`.
- `outbound_dispatches` exists with all 13 columns specified by migration `0005_stage9c_dispatch_ledger`, matching their PostgreSQL types and nullability.
- Live constraints match the migration: `outbound_dispatches_pkey`, `uq_outbound_dispatch_identity`, and the seven named check constraints for attempt bounds, lane, nonempty keys, phase, phase timestamps, resource, send/ack ordering.
- This confirms the ledger's **shape**, not its contents, indexes, retention policy, active writers, or migration safety. Those require separate read-only checks before any DDL.
- Schema compatibility choice: prefer adding a per-physical-call ordinal to the existing ledger with a new uniqueness rule, or an equivalent additive design, but verify historic rows and downstream consumers first. Do not drop `uq_outbound_dispatch_identity` until compatibility is established.
- The operator's read-only query did not report any dispatch rows or traffic counts; no production activation is authorized.

## Production ledger census (operator read-only query, 2026-10-14)
- `outbound_dispatches` has **0 total rows**, with **0** in each phase: `admitted`, `may_have_sent`, `acknowledged`, `ambiguous`.
- No historic dispatch rows need transformation at this checkpoint. Do not assume this remains true when a migration is eventually deployed; migration must remain safe if rows appear in the meantime.
- Preserve the current rnt-01 drained state; this census does not validate dispatch authorization.
