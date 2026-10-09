# Stage 9C rolling-hour boundary audit — 2026-10-08

Status: **SOURCE AUDIT AND IMPLEMENTATION DESIGN ONLY. No runtime SQL change or activation authorization.**

## Authoritative policy

`docs/phase5b-step9-production-activation-plan.md` forbids more than **1,296 automatic background starts in any rolling hour**. The frozen Stage 9B cutover (`2026-10-08T00:47:34.757784+00:00`) and exclusive event boundary (`11558`) delimit Stage 9C audit evidence; neither resets the physical-start budget.

## Verified source discrepancy

- `scripts/phase5b_stage9c_watchdog.py::inspect` reads `collection_events WHERE event_id > :boundary`. It uses that same event set for physical start/terminal reconciliation, abort-event detection, and rolling-hour calculation. Therefore a pre-boundary start inside a subsequent hour is invisible to its budget maximum.
- `scripts/phase5b_step9_checkpoint_audit.py` likewise reads background start events with `event_id > :boundary` and calculates its reported rolling maximum from those rows. It is a historical checkpoint report, not independent cross-boundary budget evidence.
- Both use the strict one-hour cutoff `timestamp > current_start - 1 hour` (events exactly one hour apart do not share a window). Preserve this policy in regression tests.
- The watchdog's event reconciliation includes all event types before applying lane/resource filtering; the Step 9 checkpoint audit filters `lane='background'`, `event_type='collection_attempt_started'`, and `resource=ANY(RESOURCES)`. Do **not** broaden the budget to interactive or unsupported-resource starts by accident.

## Proposed minimal implementation

1. Preserve the current post-boundary query and its attempt/terminal reconciliation, throttle detection, and foreign-collector checks. Do not alter the frozen boundary.
2. For budget calculation only, query eligible `collection_attempt_started` events in a bounded time window anchored to database time, including pre-boundary rows. For a watchdog inspection at `db_now`, inspect at least the preceding hour. To detect historical overages that occurred after Stage 9C began, also evaluate starts from the Stage 9C activation time onward, plus a one-hour lookback before activation. Avoid an unbounded full-table scan.
3. Use the same 1,296 ceiling and strict 60-minute rolling cutoff; order by `occurred_at, event_id`. Keep the per-run audit counts distinct from budget counts in logs.
4. Check the actual `collection_events` schema/indexes and the production scheduler's physical-start accounting before implementing SQL. Verify the event timestamp is suitable for physical-start budgeting; if event persistence can lag or be missing, document what the watchdog can and cannot prove.
5. If the required history cannot be read or is inconsistent, refuse to renew the watchdog lease. Do not interpret a missing historical window as zero traffic.

## Required offline regression matrix

- 1,296 eligible starts straddling boundary, plus one post-boundary start within the hour => reject 1,297.
- Exactly 1,296 straddling boundary => accept.
- Starts exactly one hour apart => not concurrent under existing strict cutoff.
- Interactive and unsupported-resource events do not consume this background ceiling.
- Event ID order differing from timestamp order => timestamp ordering controls rolling calculation.
- Empty or missing pre-boundary history => explicitly distinguish valid zero history from unavailable/uncertain history.
- The frozen boundary still controls Stage 9C terminal/physical reconciliation and abort-event scanning.
- Guard/lease renewal is withheld on an overage or failed budget query.

## Activation status

The four scratch PostgreSQL abort/drain checkpoints passed on commit `59f3a1f`. This source audit does not extend that evidence to rolling-budget correctness or full watchdog execution. No real collector, materializer, systemd service, database migration, or six-hour trial is authorized.


## Implementation reconciliation — 2026-10-08 (current branch)

The original discrepancy and proposal above are retained as historical design rationale, **not the current implementation status**. The Stage 9C watchdog now queries eligible physical background starts across the event boundary using a bounded database-time window, including pre-supervision starts, and computes the rolling maximum over the persisted supervision interval plus its trailing-hour context. `main()` explicitly passes the persisted run `started_at` to `inspect()` and refuses absent or invalid timestamps. The frozen Stage 9B cutover and exclusive event ID remain the materialization and post-boundary reconciliation fences, **not** a rolling-budget reset.

Verification evidence: the rolling-budget PostgreSQL scratch harness passed 10 cases; the actual watchdog `main()` scratch harness passed four scenarios including a 1,297-start violation and fenced abort/drain. See `docs/phase5b-stage9c-readiness-review.md`. These tests do **not** establish the completeness of the live event ledger or scheduler enforcement.

### Historical Step 9 audit is not a Stage 9C budget authority

`scripts/phase5b_step9_checkpoint_audit.py` remains deliberately pinned to revision `0003_request_gates` and computes its `rolling_1h_max_physical_starts` only from `event_id > since_event_id`. Its output can understate a cross-boundary peak and **must not** be used alone to authorize Stage 9C. Preserve the script as historical Stage 9B evidence. Do not widen its schema acceptance or repurpose its PASS verdict.

A future Stage 9C-specific **read-only** audit should:

1. Require the expected target DB, writable primary, exact revision `0004_stage9c_supervision_runs`, and explicit frozen cutover/event boundary. Read the exact authorized run's persisted `started_at` and deadline rather than inventing a new cutover.
2. Inspect all eligible physical background-start events from `started_at - interval '1 hour'` through the checkpoint time, using `occurred_at, event_id` ordering. Evaluate the strict trailing-hour maximum over the Stage 9C supervision interval, including the pre-supervision context and any peak that has since expired.
3. Keep the post-boundary event ledger reconciliation, throttle/persistence checks, identity validation, and queue/provenance inspection separate from the rolling-hour budget dataset; never interpret a missing table, failed query, or unverifiable event coverage as zero starts.
4. Compare physical-start event evidence with scheduler claim/attempt accounting and known persistence failure modes. Explicitly report coverage and uncertainty; fail closed if a complete budget cannot be established.
5. Use bounded queries with reviewed indexes and a documented query-time budget. No mutation, migration, scheduling, collector startup, or Battlelog requests.

**Current decision:** design reconciliation documented; Stage 9C-specific checkpoint tool and live-ledger completeness audit remain pending. HOLD.
