# BF4PS — bounded live cohort runner design (2026-10-11)

**Design-first checkpoint. Implementation candidate, not fleet activation.**

## Goal
Turn the first successful live detailed-stat PostgreSQL persistence proof into a repeatable, bounded, observable collector run for an explicit set of existing soldier identities. Extend to weapons/vehicles only after each resource has a persisted live proof. Use existing BF4PS collector/queue/persistence modules, not obsolete phase-specific runners.

## Preconditions
1. Operator explicitly authorizes live Battlelog collection (given 2026-10-11).
2. Verify database name, role, primary/read-write status, actual Alembic revision, and documented schema against migrations. Never silently migrate or use a production DB.
3. Identify and confirm all running BF4PS collectors/queued jobs before starting; ensure the test cannot consume another worker's work.
4. Require a finite explicit persona/platform cohort, resource allowlist, maximum total HTTP attempts, and nonzero per-egress interval. Default to one host and conservative volume. Refuse absent or ambiguous limits.
5. Separate repeatable-run accounting from historical events; preserve lifetime and rolling-hour ceilings globally rather than resetting them for each invocation.

## Execution
- Materialize only the requested cohort and resource jobs, with idempotent existing-soldier lookup/upsert.
- Use normal job claim, lease, request admission, physical-attempt ledger and collector functions. Avoid bypassing admission by calling fetch directly in a scaled runner.
- Stop on cap, drain, database unavailability, or loss of ownership; no automatic free retry, redirect, or stale queued-send.
- Commit stats, history, state, events, and queue finalization atomically.
- Produce an immutable run manifest, per-resource counts, and verification SQL output without credentials.

## Acceptance
- Per-soldier success/failure/unavailable counts reconcile with durable events.
- Every successful detailed collection has current stats, expected history change behavior, successful state, finalized queue, and source timestamp.
- Repeated unchanged fetch updates current timestamp without a duplicate history snapshot.
- Weapons and vehicles each pass a live persisted cohort before mixed-resource batch.
- Per-egress pacing and global attempt accounting checked before, during, after.
- Abort without widening cohort or enabling fleet when any check fails.

## Boundary
Existing scratch integration DB at revision 0004 now contains retained real PC detailed statistics for persona 236753552. The previous empty-database-only proof harness is intentionally **not rerunnable** on this populated target. D2 synthetic scratch at 0005 remains separate. No host firewall/gateway/network rearchitecture. BF4SW untouched. Production distributed fleet remains HOLD pending bounded-run validation.

## Immediate implementation
1. Read current detailed/weapon/vehicle collector entrypoints, scheduler and schema/migrations.
2. Add CLI bounded runner and offline tests on the feature branch.
3. Run dry-run/read-only preflight against selected test DB.
4. Run one repeat collection to prove history deduplication, then a small PC/multiplatform cohort.
5. Expand cautiously, retaining run evidence.
