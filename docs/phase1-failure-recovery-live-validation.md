# Phase 1 detailed failure/recovery live validation

Date: 2026-10-04 UTC

## Scope

This record captures the live test-database validation of the Phase 1 detailed collector's retryable-failure semantics and subsequent recovery path.

The validation used the existing naturally discovered PC soldier `mauirixxx` (`persona_id=236753552`, `soldier_id=1`) in `bf4_playerstats_test`. The database was confirmed writable and not in PostgreSQL recovery.

## Controlled failure

The harness deliberately injected one `DetailedStatsTransportError` after the queue job had been claimed and transitioned to `running`. No Battlelog HTTP request was made for the injected failure.

The failure was classified as `battlelog_transport` and persisted through the same atomic retry-failure path used by the detailed collector.

Live validation proved all of the following simultaneously:

- `detailed_stats_current` remained unchanged;
- `detailed_stats_history` remained unchanged;
- the previous detailed last-success timestamp was preserved;
- `collection_state.detailed_state` became `temporary_failure`;
- the detailed consecutive-failure count incremented;
- the structured error class was retained;
- a `collection_failure` event was appended;
- the queue job returned to `pending` with a future eligibility time;
- collector ownership and the lease token were cleared;
- the failed attempt therefore remained safely recoverable without corrupting last-known-good statistics.

## Recovery

The same queue job was then made immediately eligible and passed through the normal detailed collector orchestration. This recovery invocation performed a real Battlelog detailed-statistics request.

Observed recovery result:

- Battlelog collection succeeded;
- duration was 752 ms;
- `collection_state.detailed_state` returned to `success`;
- the consecutive-failure count reset to zero;
- the previous error class/message were cleared;
- a `collection_success` event was recorded;
- the queue job was finalized and removed;
- `history_appended=False`, correctly reflecting that the canonical retained statistics had not changed.

Temporary request-gate and collector registry rows created by the harness were removed successfully. Statistics, collection state, and collection events were intentionally retained as validation evidence.

## Acceptance result

`BF4PS PHASE 1 FAILURE / RECOVERY: PASS`

This validates the Phase 1 invariant that a retryable detailed-statistics collection failure preserves last-known-good player statistics while recording structured failure state and leaving work recoverable. It also validates that the same work can subsequently recover through the normal Battlelog success path and return collection state to healthy without manufacturing duplicate history.

With queue lease/fencing, request pacing, multi-platform live collection, canonical history comparison, atomic success persistence, and retryable failure/recovery now validated, the next implementation boundary is the continuously running detailed collector worker lifecycle and scheduling loop.
