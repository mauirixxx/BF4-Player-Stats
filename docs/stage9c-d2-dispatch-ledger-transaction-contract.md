# Stage 9C D2 — durable dispatch ledger transaction contract

**Status:** proposal, not approved implementation. **Production HOLD.** Derived from the documented current schema, Alembic migrations 0001/0003/0004, and inspected `bf4ps/background_service.py` and `bf4ps/request_gate.py`. No scratch SQL writes or migrations were executed for this document.

## Existing concurrency boundaries

- `claim_production_background_job` takes transaction advisory lock `pg_advisory_xact_lock(hashtext('bf4ps:phase5b-background-service'))` **before** reading budget usage and claiming a queue row. Any future background dispatch admission must serialize against this exact authority or replace it in a coordinated migration; a second independent lock is unsafe.
- Current `_usage` sums rolling-hour `collection_attempt_started` events and unexpired claimed/running reservations **without** a matching start event. A started event and reservation already have exclusion logic. A third source must not be naively summed.
- `reserve_request_slot` independently locks `request_gates` by egress key and reserves a future timestamp. Its `wait_for_permit` runs after transaction commit. **A permit may be scheduled in the future:** admission-time clock is not necessarily actual send time.

## Proposed ledger schema (not an existing table)

Candidate `outbound_dispatches` columns:

| Column | Candidate contract |
|---|---|
| `dispatch_id` | UUID primary key |
| `job_id` | bigint, references current job only if retention policy supports it |
| `attempt_number` | integer >= 0 |
| `resource` | text, constrained to supported outbound resources |
| `lease_token` | UUID |
| `collector_uuid` | UUID |
| `egress_key` | nonempty text |
| `lane` | background / interactive |
| `admitted_at` | timestamptz, assigned by PostgreSQL clock |
| `phase` | admitted / may_have_sent / acknowledged / ambiguous |
| `send_marked_at` | nullable timestamptz, set before transport |
| `acknowledged_at` | nullable timestamptz |
| `payload_fingerprint` | stable digest binding identity to request payload |

Candidate unique identity: `(job_id, attempt_number, resource, lease_token)`. Duplicate identity with mismatched payload/egress/collector is **rejected**, not silently treated as successful replay. Retention must outlive possible job retry/replay, not just one hour. Decide job FK delete behavior explicitly: cascading removal of dispatch evidence would be dangerous.

## Admission transaction — candidate order

1. Begin transaction with documented isolation level; acquire the **existing background advisory transaction lock**.
2. Look up existing identity; return **duplicate/denied**, never a second send grant. Reject identity collisions with different payload/egress/owner.
3. Lock and verify `collection_jobs` row: job id, lane, resource, attempt, collector, token, running state, and database-time unexpired lease.
4. Check active Stage 9C supervision guard and global admission budget. Do not claim that this alone prevents a late send.
5. Reconcile outstanding reservations, started events, and durable dispatch records under one documented budget rule. Count distinct logical attempts, but **never** choose timestamps that understate actual potential sends.
6. Insert durable admission identity and commit. Any DB failure/timeout leaves caller without send authorization until a subsequent read resolves committed-vs-rolled-back ambiguity.
7. Separately and durably mark `may_have_sent` **before** fake transport. On uncertainty, refuse replay. A transport failure is not permission to try again under the same identity.

## Mandatory decisions before implementing migration

**A. Rolling-hour accounting timestamp:** The current `collection_attempt_started.occurred_at` and candidate `admitted_at` can differ. Pure deduplication by identity (as characterized by `dispatch_budget_model.py`) is **not sufficient** when one record ages out before another. Define authoritative physical-dispatch time or conservatively account for all relevant active windows. Even the conservative window cannot prevent an arbitrarily delayed real send.

**B. Pending reservations:** Current claim logic may hold a slot while no dispatch row exists. Once dispatch exists, the claim reservation must not be counted twice, including across lease expiry and job reclaim.

**C. Egress pacing:** `request_gates.next_request_at` can be later than admission. Decide whether dispatch is forbidden if permit time exceeds lease or budget authorization window. Never hold the global advisory lock during sleeps or HTTP.

**D. Physical-send atomicity:** PostgreSQL cannot atomically commit with a separate TCP/HTTP send. `may_have_sent` before transport prevents replay, but cannot stop a paused process from sending late. The hard guarantee of 1,296 *actual sends* in every rolling hour is **UNPROVEN** and must not be labeled PASS.

**E. Connection/clock:** Use PostgreSQL clock timestamps for budget/lease decisions; transaction `now()` is fixed at transaction start and can become stale while waiting on advisory locks. Capture `clock_timestamp()` **after** acquiring the lock.

**F. Lock order and lifecycle:** Establish consistent order global advisory lock -> job row -> per-egress gate row (if combined). Verify deadlock risk with existing collector paths before integration. Define behavior when supervision aborts or ownership is lost between admission and send.

## Safe next tests

1. Read-only schema introspection on the explicitly identified scratch database; compare columns, indexes, constraints and Alembic revision with reference and migrations.
2. Offline deterministic tests for split timestamps, duplicate identity with conflicting payload, and stale clock after lock wait.
3. Only after contract review, design an **isolated scratch migration** and test two independent PostgreSQL transactions with fake transport; no real HTTP, no production migration.
