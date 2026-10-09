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

## Next implementation gate — reservation-to-start transition (design checkpoint, 2026-10-08)

**Status: designed, NOT implemented or executed.** The preceding claim-race PASS must not be conflated with this gate.

### Authoritative code and schema

- `bf4ps/background_service.py::_usage` counts rolling-hour `collection_attempt_started` rows plus claimed/running jobs **without a matching start event for their current attempt number**.
- `bf4ps/collection_jobs.py::claim_next_job` increments `attempt_count` and issues a new `lease_token` on claim; `mark_job_running` enforces ownership, lease token, status, and expiry.
- `docs/database-schema-reference.md` defines `collection_events` (including `job_id`, `attempt_number`, `lease_token`, `resource`, `lane`, `metadata`) and `collection_jobs` ownership/lease constraints. Review migration chain `0001`–`0004` and actual production start-event writer before authoring INSERT statements. Do not infer writer metadata.
- Existing `scripts/phase5b_stage9c_claim_race_scratch.py` provides a successful two-connection claim and exact-marker cleanup pattern, **not** a reusable production start-event writer.

### Scenario A: committed reservation becomes one durable start

1. Refuse anything but the allowlisted, empty, writable Stage 9C scratch database at revision `0004_stage9c_supervision_runs`. Verify `READ COMMITTED`. No HTTP.
2. Insert only uniquely marked, FK-valid fixture collectors, soldier, pending job, and 1,295 synthetic rolling-hour started events. Record baseline `_usage` = 1,295.
3. Call the **production** background claim path in a transaction, commit, and assert `_usage` = 1,296 via an independent connection (one unstarted reservation).
4. Transition to `running` using production `mark_job_running` with the original ownership tuple. Insert the **matching** durable `collection_attempt_started` event using the verified production writer shape (same job ID and attempt number), then commit.
5. On a fresh transaction assert `_usage` = 1,296, with one matching started event and **zero outstanding reservation for that attempt**. An additional eligible background job must not be admitted at the ceiling.
6. Verify stale or incorrect lease-token attempts cannot transition the job to running or write a valid owned start. The writer's fencing semantics must be reviewed; do not assume SQL constraints alone enforce this.
7. Delete only uniquely marked fixtures, validate exact deletion counts transactionally, and independently verify the five scratch tables are empty.

### Scenario B: rollback and durability boundaries

- Roll back a transaction containing an **uncommitted** start event: the existing claimed/running reservation must remain counted (1,296). Do not simulate a physical request in this case.
- Once a matching start event is **committed**, later normalization/persistence rollback must not erase it. Validate against actual writer transaction boundaries; do not claim physical-attempt completeness from synthetic SQL alone.
- Ensure no event is inserted twice for the same physical attempt by the production path. A duplicate synthetic event would expose whether `_usage` double counts and must be treated as a possible defect, not silently hidden.

### Review-before-execution checklist

- Verify production event writer, metadata fields, lease fencing, and commit boundaries from source.
- Verify migration constraints and live scratch revision; do not modify production or apply migrations.
- Prefer a separate scratch harness rather than changing the already-passing claim-race harness.
- Include compile/offline tests, explicit `--execute`, a target allowlist, crash/partial-seed behavior, exact marker cleanup, and independent post-run emptiness check.
- On any failure, stop and inspect before retrying. Stage 9C production six-hour trial remains **HOLD**.

### Production detailed start-writer source review — 2026-10-08

Reviewed `bf4ps/detailed_collector.py` and `bf4ps/background_service.py` against the documented `collection_events` and `collection_jobs` schema:

- `collect_one_detailed_job` claims and transitions the job to running in a committed transaction, reserves the request gate separately, then calls `_record_detailed_attempt_started` before `fetch_detailed_stats`.
- `_record_detailed_attempt_started` opens an independent `engine.begin()` transaction, selects the running job `FOR UPDATE` with matching job/soldier/collector/token and unexpired lease, and inserts a durable `collection_attempt_started` event with `physical_request=true`, priority class, retry flag, and job attempt number. It commits before HTTP.
- **Unresolved duplicate-start risk:** the writer shown does not itself query for an existing matching start event or use an `ON CONFLICT` clause. `_usage` counts all rolling-hour start-event rows, not distinct attempts. Do not assert idempotency or absence of duplicate starts without reviewing migration constraints and exercising the production writer. A duplicate event might conservatively overcount; it must still be classified as a correctness defect if one physical attempt is charged twice.
- Next implementation must test the production detailed writer, not only a hand-authored SQL insert. A direct second writer invocation is a fault-injection scenario, **not** evidence that normal runtime makes two HTTP requests. Test no HTTP and assert explicit event count.
- Verify weapons and vehicles start-writer equivalents before claiming cross-resource transition coverage. **No scratch execution performed in this source review.**

## Expired lease reclaim — source review checkpoint (2026-10-08)

Source-verified against `bf4ps/background_service.py::_usage` and `claim_production_background_job`, `bf4ps/collection_jobs.py::claim_next_job`, and the documented lease shape in `docs/database-schema-reference.md`:

- `_usage` charges every `claimed` or `running` background job without a matching start event for its **current** attempt, regardless of whether `lease_expires_at <= now()`.
- `claim_next_job` permits reclaiming an expired claimed/running job, resets its claim/start fields, increments `attempt_count`, and issues a new lease token. It uses row locking and `SKIP LOCKED`.
- The aggregate budget decision precedes the reclaim operation. **Potential capacity deadlock:** if the ceiling is fully consumed and an unstarted reservation expires, its existing charge can prevent the admission path from reaching the reclaim that would replace it. This is a source-level hypothesis; test it on scratch before changing production code.
- For an **already started** expired lease, the previous durable start event remains charged for the rolling hour. A reclaimed attempt requires another admission slot and a new lease token. Old-token writes must be fenced out.

### Next scratch test plan (not yet executed)

1. Use a fresh empty, allowlisted scratch DB at documented migration head. Seed a uniquely marked collector, soldier, pending detailed job, and exactly 1,295 synthetic started events. Admit and commit one unstarted claim (usage 1,296).
2. In a scratch-only transaction, force that lease expiration using DB time, without sleeping or calling HTTP. Verify its old ownership token and the unchanged usage count.
3. Attempt production background admission for the same expired job. Record whether it returns `None` at the ceiling. **This may be the expected red test**; do not silently alter assertions or claim a pass.
4. In a separate below-ceiling fixture, reclaim an expired unstarted lease, confirm `attempt_count` increments and `lease_token` changes, old token cannot mark running or write a durable start, and the replacement reservation is charged only once.
5. In a separate started-lease fixture, record a durable production start event, expire its lease, reclaim below the ceiling, and verify both the old physical attempt and the new reservation are charged (two slots). Test old-token fencing.
6. Include transaction rollback, exact marker-owned cleanup, no HTTP, and independent five-table emptiness verification. Do not touch production or remote hosts.

**Gate:** no production activation; Stage 9C remains HOLD. If the full-ceiling case fails, first document the reproduced behavior and design the fix before implementation.
