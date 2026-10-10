# Stage 9C T4/T5 — lease-expiry and physical-start safety test design

**Status:** DESIGN / NOT EXECUTED. **Production:** HOLD / NOT AUTHORIZED. No real Battlelog HTTP.

## Source review (branch fix/stage9c-t4-inspector-lease-expiry)

The three resource collectors (`bf4ps/detailed_collector.py`, `bf4ps/weapon_collector.py`, `bf4ps/vehicle_collector.py`) follow the same structure: production-budget claim; transition to running; commit egress request-gate reservation; wait if required; commit a lease-fenced `collection_attempt_started` event; then invoke the resource-specific fetch function **outside that database transaction**. The start transaction uses `FOR UPDATE` and rejects stale tokens/expired leases and duplicate physical-start events for the same job attempt. Once the transaction commits, no lock is held during the call to `fetch_*_stats`.

This is a **real time-of-check/time-of-use window**, not proof of an observed over-budget HTTP request. A start event can predate the actual HTTP request; if the worker pauses for longer than a rolling hour, its start event can age out before the delayed request begins. A different worker can meanwhile use the freed hourly capacity. Therefore the 1,296-start ledger alone cannot prove a strict *actual outbound request* limit for arbitrary pauses. An extra lease check after commit does not atomically close the window.

## Required invariants and proposed deterministic tests

1. **Pre-start expiry:** pause after claim/egress gate, advance PostgreSQL time beyond lease expiry, attempt physical-start transaction; it must reject, commit no physical-start event, and issue no HTTP.
2. **After committed start / before fetch:** pause exactly after the physical-start transaction commits, expire/reassign the lease, then resume the old worker. Record whether the old fetch is still reachable. Under current source, it appears reachable; test must fail closed as an explicit known risk rather than falsely asserting safety.
3. **Fresh replacement:** after lease expiry, new worker may claim the eligible job (new attempt number and token). Old worker must not be able to finalize or mutate the new owner's state. Recheck failure/retry persistence paths.
4. **Rolling-hour boundary:** hold an already ledgered start past the one-hour window before releasing the HTTP call; show whether the *actual* HTTP could occur after its ledger event has aged out. Use a fake fetch and controlled clock; no network.
5. **All three resources:** repeat for detailed, weapons, vehicles; do not infer safety from one resource.
6. **Ledger completeness:** compare the timestamp of actual fake outbound initiation with persisted start event, and define acceptable skew or a bounded dispatch authorization mechanism. Distinguish event-recorded intent from observed network dispatch.
7. **Database timing:** use PostgreSQL server time for lease/rolling-window decisions. Ensure deterministic barriers rather than sleep-dependent tests; verify schema and migrations against documented schema before scratch integration.

## Design decision needed before implementation

Choose and document a defensible outbound-dispatch invariant. Two possible approaches require review:

- **Bounded dispatch permit:** a durable start event reserves budget *for a strictly bounded dispatch window*, with dispatch cancellation when the deadline passes; the budget must conservatively count permits over every period in which dispatch is possible. Verify scheduling and recovery accounting.
- **Lease-held dispatch coordination:** guard the dispatch with a shared mechanism that prevents ownership transfer during the critical handoff. Holding a database transaction or row lock across an unpredictable network request is risky and should not be adopted without failure-mode analysis.

Neither option is authorized here. Simply adding a second check between commit and fetch is insufficient to guarantee atomicity.

## Execution order and gates

A. Document expected invariant and identify existing tests for each resource.

B. Add zero-network deterministic regression reproducing post-commit pause, then implement an approved narrow fix.

C. Run offline tests, then operator-approved scratch-only PostgreSQL validation with dummy fetch hooks; prove pre-start rejection, safe replacement, budget window, and no unledgered dispatch.

D. Reconcile T4 inspector proof separately from T5 actual physical-start ledger. Keep both formal gates OPEN until acceptance evidence exists.

No scratch writes, migrations, host launches, or real HTTP are authorized by this document.
