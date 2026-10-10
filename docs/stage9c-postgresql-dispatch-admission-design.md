# Stage 9C — PostgreSQL mediated-dispatch admission design (draft)

**Status:** DESIGN ONLY / NO SQL IMPLEMENTED. **Production:** HOLD / NOT AUTHORIZED. Last operator-verified baseline: 503 offline tests at `9be1623`.

## Verified source baseline

Reviewed `docs/database-schema-reference.md` and executable migrations `0001_initial_schema.py`, `0003_request_gates.py`, `0004_stage9c_supervision_runs.py` at branch `fix/stage9c-t4-inspector-lease-expiry`. Current migration head is `0004_stage9c_supervision_runs`. No live database introspection has been performed for this proposal.

- `collection_jobs` has `job_id`, `resource`, `lane`, `status`, `attempt_count`, `collector_uuid`, `lease_token`, `lease_expires_at`. Unique `(soldier_id, resource)`. It is a **mutable queue row**, not a durable dispatch-idempotency ledger.
- `collection_events` has `event_id`, `occurred_at`, `job_id`, `resource`, `lane`, `event_type`, `attempt_number`, `lease_token`, `metadata`. It is an append-style operational ledger, not a unique constrained dispatch authority.
- `request_gates` has `egress_key` PK, `next_request_at`, `updated_at`. It coordinates **pacing**, not globally unique physical-send admission.
- `stage9c_supervision_runs` is watchdog state, not a dispatch ledger. Do not overload it.

## Proposed separate ledger (requires migration and documentation before implementation)

A future `outbound_dispatches` table would record a stable request identity, job/attempt/resource/lease ownership, collector and egress identity, background-vs-interactive lane, PostgreSQL admission timestamp, conservative send phase (`admitted`, `may_have_sent`, `acknowledged`), and outcome metadata. Proposed uniqueness must be **independent of mutable queue ownership**; candidate key: `(job_id, attempt_number, resource, lease_token)`. This is a design candidate, not an existing table or approved migration.

An admission transaction should: (1) obtain the **same global coordination lock** used by background claims or a documented equivalent; (2) check idempotency **before** stale-lease rejection so replay cannot allocate a new slot; (3) verify current job owner/token/attempt/status and database-time lease validity; (4) count all conservatively budgeted dispatches in the rolling hour, including ambiguous sends and other existing physical-start reservations; (5) persist the admission identity; (6) commit before the worker can receive permission to proceed. Do not introduce two separate global budget authorities that each believe they own all 1,296 slots.

**Critical integration risk:** existing `claim_production_background_job` counts `collection_attempt_started` and live claimed/running reservations. A new dispatch ledger cannot simply be added to this count without reconciliation or it may double-count attempts; conversely, ignoring either source can undercount. Define a single authoritative accounting rule, explicit migration/backward compatibility, and concurrency lock order before SQL implementation.

## Crash, concurrency, and timing contracts to test

1. Two independent PostgreSQL connections contend for the last slot; exactly one commits admission.
2. Same dispatch identity submitted twice concurrently; at most one durable identity and at most one simulated fake send.
3. Committed admission + lost acknowledgment; retry returns existing state and never grants a second send.
4. Crash before commit; rollback leaves no durable admission and no send.
5. Crash after commit but before send; conservative budget consumed; recovery behavior must not cause unbounded stale dispatch.
6. Mark `may_have_sent` durably **before** fake transport. On restart, `may_have_sent` is terminal for automatic resend.
7. A dispatcher paused after `may_have_sent` can still issue a **late** real send: this is not solved by PostgreSQL and must remain an OPEN safety gap.
8. Boundary timestamps use PostgreSQL clock; exact one-hour cutoff, concurrent transitions, and monotonic-clock assumptions require explicit tests.
9. DB outage and partition: fail closed; no direct-HTTP fallback.
10. Per-site egress identity and per-egress pacing remain enforced; avoid collapsing traffic onto one public IP.

## Next gated implementation sequence

**D1:** Write pure concurrency/state-machine tests (zero HTTP) that characterize crash and double-admission semantics, including a deliberate failing/known-gap test for the late-send boundary.

**D2:** Design a migration for a separate ledger and reconcile the existing claim/start accounting, using schema-reference and migrations as source of truth. Do not implement until D1 and contract review.

**D3:** Operator-approved scratch PostgreSQL validation with two independent connections/hosts and fake transport. Verify schema introspection against docs first; no real HTTP.

**D4:** Decide whether the strict actual-HTTP rolling-hour guarantee is achievable under the stated failure model. An application-level transaction plus subsequent network send cannot provide arbitrary-pause atomicity. If strict under arbitrary pauses is non-negotiable, an enforcement boundary closer to the network or an explicit redesign is required.

No database writes, schema migrations, worker launches, or production traffic are authorized by this document.
