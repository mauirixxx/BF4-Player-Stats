## Reconciliation with completed Stage 9C work (2026-10-08)

**Do not duplicate previously executed checks.** Existing evidence and implementation are recorded in:

- `docs/phase5b-stage9c-readiness-review.md` — 406/406 offline PASS; 22 PostgreSQL scratch checks; actual watchdog `main()` isolated integration; unresolved activation gates.
- `docs/phase5b-stage9c-rolling-budget-boundary-audit.md` — cross-boundary rolling-hour accounting implemented and verified, with explicit remaining live-ledger completeness caveat.
- `scripts/phase5b_stage9c_rolling_budget_scratch.py`, `scripts/phase5b_stage9c_watchdog_main_scratch.py`, `scripts/phase5b_stage9c_checkpoint_scratch.py` — reusable allowlisted PostgreSQL scratch validation patterns.
- `scripts/phase5b_background_service_db_validate.py` — rollback-only sequential production-admission checks, **not** concurrent admission proof; currently pins historical revision `0003_request_gates`, so do not execute against the Stage 9C scratch target unchanged.
- `scripts/phase3a_concurrent_claim_integration.py` and `scripts/phase3b_lease_fencing_integration.py` — existing concurrency/lease primitives to inspect before building new tests.

**Incremental scope only:** race two independent transactions through `claim_production_background_job` at 1,295/1,296 usage; verify reservation-to-start transition, expired lease reclaim, retry consumption, and cross-resource accounting. Preserve existing allowlist, exact target checks, no external HTTP, and Stage 9C HOLD. Prior PASS results are historical operator evidence, not tests rerun in this branch.

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

## Execution checkpoint — 2026-10-08

The first real scratch claim-race scenario **PASSED** on `tcou` at tested commit `821dfb5`: 1,295 synthetic start events, one committed weapons claim reserving slot 1,296, competing vehicles claim denied, lease reconciled, and marker-owned fixture cleanup. Independent post-run verification found all five scratch tables empty. Offline tests: 6 targeted and 412 total PASS. Full command, environment, output, and limitations: [execution record](stage9c-admission-concurrency-execution-2026-10-08.md).

**Not yet validated:** reservation-to-start event transition, reclaim of expired unstarted/started leases, retry and mixed-resource consumption, rollback/failure injection, and hour-boundary expiry. This checkpoint closes only the specified two-transaction claim race, not the whole admission gate. Production Stage 9C remains **HOLD**.
