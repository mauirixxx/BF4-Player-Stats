# Phase 2 drained runtime live validation

Date: 2026-10-04 UTC

## Scope

This record captures the live PostgreSQL validation of the Phase 2 collector registration, heartbeat, operator-control, restart, and clean-stop boundary against `bf4_playerstats_test` on `tcou`.

This validation intentionally remained below the automatic-work boundary. It performed no feeder pass, no queue claim, and no Battlelog request.

## Test identity

The harness used the stable test collector identity:

- collector UUID: `5d69618d-0c16-4c5f-96e5-b5a18ea948c4`;
- collector name: `phase2-drained-tcou`;
- hostname: `tcou`;
- lane: `background`;
- egress key: `phase2-drained-tcou`.

The database was `bf4_playerstats_test` and `pg_is_in_recovery()` was false.

## Registration and operator control

The harness registered the stable identity, then deliberately set the collector to `drained=true` as an operator-owned control state.

Subsequent heartbeat/control reads reported the collector enabled but drained, so `may_claim` remained false.

Two successful heartbeat refreshes were observed at:

- `2026-10-04 05:16:58.648448+00:00`;
- `2026-10-04 05:16:58.650266+00:00`.

The heartbeat state remained healthy while drained.

## Restart validation

A normal process restart was simulated by registering the exact same configured collector UUID and identity again.

The restart preserved:

- the stable UUID;
- the operator-owned `enabled=true` state;
- the operator-owned `drained=true` state.

The registration path therefore did not silently undrain the collector or invent a replacement runtime identity.

## Queue/event isolation

The total `collection_jobs` row count was unchanged across the validation.

The total `collection_events` row count was also unchanged. Routine registration and successful heartbeat activity did not generate collection events.

This confirms that a drained runtime can maintain liveness/control state without materializing or claiming collection work.

## Clean stop

The clean-stop path changed the collector heartbeat state to `unknown` while preserving the operator controls (`enabled=true`, `drained=true`).

The deliberately drained test collector row was retained after the harness for operator inspection.

## Acceptance result

`BF4PS PHASE 2 DRAINED RUNTIME INTEGRATION: PASS`

Validated properties:

- stable collector registration: PASS;
- drained state blocks claims: PASS;
- repeated heartbeat refresh: PASS;
- heartbeat remains healthy while drained: PASS;
- restart preserves stable UUID: PASS;
- restart preserves operator drain state: PASS;
- queue rows unchanged: PASS;
- collection events unchanged: PASS;
- clean-stop state transition: PASS;
- controls survive clean stop: PASS;
- feeder passes: 0;
- job claims: 0;
- Battlelog requests: 0.

This completes the Phase 2 registration/heartbeat/control validation boundary. The next design-approved step is a tiny bounded automatic-work cohort: feeder materialization followed by runtime consumption through the existing fenced queue and PostgreSQL request gate.
