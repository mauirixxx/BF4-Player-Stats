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
