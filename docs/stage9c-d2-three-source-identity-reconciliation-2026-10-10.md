# Stage 9C D2 — three-source identity reconciliation contract (2026-10-10)

**Status: design gate, NOT implemented SQL or authorization to send HTTP. Production HOLD.**

Reviewed: `docs/database-schema-reference.md`, `migrations/versions/0001_initial_schema.py`, `0005_stage9c_dispatch_ledger.py`, `bf4ps/background_service.py`, `bf4ps/dispatch_budget_model.py`. Existing T4 scratch remains at 0004; dedicated D2 at 0005.

## Confirmed identity fields

| Source | Identity fields | Critical limitation |
|---|---|---|
| `collection_events` with `event_type='collection_attempt_started'` | `job_id`, `attempt_number`, `resource`, `lease_token` | **All four nullable**; `occurred_at` has a default `now()` (transaction start) |
| `collection_jobs` claimed/running | `job_id`, `attempt_count`, `resource`, `lease_token` | Token nullable in general, but lease-shape constraint requires it for claimed/running; row mutable on reclaim |
| `outbound_dispatches` | `job_id`, `attempt_number`, `resource`, `lease_token` | All required, positive attempt; immutable ledger identity via unique constraint |

**Important correction to prior uncertainty:** all three sources *do* expose the same four logical identity dimensions, but historical started events may have missing components. A SQL join using nullable equality can silently fail to reconcile them. Never treat a missing component as an exact identity match. Never infer missing lease token from the current mutable job row: reclaim can change it.

## Conservative budget policy to implement/test

1. Under the existing transaction advisory lock `pg_advisory_xact_lock(hashtext('bf4ps:phase5b-background-service'))`, sample `clock_timestamp()` after lock acquisition. Use one timestamp for all window and lease predicates; do not rely on `now()` after waiting for a lock.
2. Collect background started events with `occurred_at` in the active rolling window; active claimed/running reservations with unexpired lease; background dispatch ledger rows whose `admitted_at` is in the active window.
3. Fully populated identities can be grouped across the three sources; count one identity once **if any evidence is active**. Each started event missing any identity component must consume a separate conservative unit (even if this overcounts). Duplicate started events with the same complete identity are a separate integrity question: do not silently erase evidence of multiple possible sends.
4. Never use a mutable current job row to retroactively repair an old event. A reclaimed job's new token represents a new attempt identity.
5. Maintain fairness class accounting separately. Dispatch ledger does not currently persist priority class, so the ledger alone cannot classify active/bootstrap/recovery. Avoid inventing class assignment or bypassing class limits.
6. Account for timestamps from different sources aging out at different times. The identity-set model is an admission accounting approximation, **not** a hard actual-send bound.
7. Concurrent transactions with distinct identities must use the **same lock**, and the next transaction must see the committed first insertion. Test with actual SQL and seeded synthetic events/reservations only after a review of transaction isolation and cleanup.

## Explicit unresolved blockers

- **Actual HTTP late-send:** a process can pause after admission and send outside the admission-time window. Durable ledger admission alone cannot guarantee ≤1296 physical sends in any rolling hour.
- **Started event timing:** `now()` default is transaction-start time, not guaranteed physical-send time. Existing code path needs inspection before relying on `occurred_at`.
- **Class attribution:** dispatch ledger has no priority-class snapshot. Must reconcile with historical events/jobs or conservatively deny when attribution cannot be proven.
- **Multiple sends under one identity:** identity deduplication is valid only if the transport implementation prevents replay. That remains unproven.

## Next implementation order

1. Offline deterministic unit tests for null-key events, reclaimed lease, timestamp split, duplicate started records, and class attribution uncertainty.
2. Implement a read-only SQL reconciliation query against D2; compare it with the pure model on synthetic data, including incomplete identities.
3. Only then add isolated transactional admission tests for distinct identities at the final slot; keep collector and HTTP integration disabled.
