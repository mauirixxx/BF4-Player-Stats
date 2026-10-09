# Stage 9C — PostgreSQL admission concurrency validation

Status: **HOLD — validation design only; no live activation**

## Baseline

Branch: `feature/phase5a-cost-cohort`. Schema reference: `docs/database-schema-reference.md`; migrations `0001` through `0004`. Current head `0004_stage9c_supervision_runs`.

The production background service uses a transaction-scoped advisory lock around an aggregate rolling-hour usage query and queue claim. Usage combines committed `collection_attempt_started` events with currently claimed/running jobs that have no matching start event for their attempt number. Detailed, weapons, and vehicles use the same admission function in opt-in production-budget mode.

## Critical concurrency questions

1. At 1,295 counted attempts, start two or more independent database transactions simultaneously. Exactly one additional background claim may commit.
2. Hold the winning claim transaction open; the losing transaction must wait and observe the committed reservation, not a stale count.
3. Reserve an unstarted claim and verify it consumes a slot; commit the matching start event and verify it counts exactly once.
4. Expire and reclaim a lease without an HTTP start event; verify ownership fencing and no double-counting of the replacement claim.
5. Expire and reclaim after a durable start event; the previous physical attempt must remain charged for the rolling hour, and any replacement attempt must consume a new slot.
6. Repeat with mixed detailed, weapons, vehicles, and retries, across distinct collector identities.
7. Inject transaction rollback, start-event insertion failure, and failed post-request persistence; verify fail-closed admission and retained physical-attempt evidence where the request occurred.
8. Exercise the exact one-hour boundary and confirm old events age out without treating outstanding reservations as free.

## Harness safety requirements

- Run only against an isolated PostgreSQL database migrated to the documented Alembic head; never production.
- Verify schema and migration revision before seeding or executing tests.
- Register actual collector identities and create valid soldiers/jobs using documented columns and constraints; no invented schema.
- Use independent PostgreSQL connections and explicit transaction barriers. A single connection or mocked advisory lock is not a concurrency test.
- Stub outbound HTTP completely. No live Battlelog, Keeper, or BFLIST requests.
- Snapshot and assert event counts, reservation counts, queue ownership, and outcomes after each barrier.
- Fail loudly on any unexpected request, ambiguous result, or schema mismatch.
- Preserve Stage 9C HOLD until tests and operational review pass.

## Gate

Pass requires reproducible green integration evidence for all scenarios, with no aggregate oversubscription and no uncharged physical attempt. A failure is a blocker to rollout, not permission to relax the 1,296/hour cap.

## Potential issue to investigate before harness implementation

The rolling-hour query filters start events by `occurred_at`, while outstanding reservations are counted without an age filter. Verify the intended behavior for expired, unstarted claims and whether a later reclaimed attempt changes the counted reservation. The test must distinguish **admission reservation** from **actual physical request**; they are not interchangeable.
