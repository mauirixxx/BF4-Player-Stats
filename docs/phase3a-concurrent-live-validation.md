# BF4PS Phase 3A concurrent live validation

Status: **PASS — retained live evidence**

Date: 2026-10-04 UTC

Phase 3 design reference: `docs/phase3-distributed-collector-design.md`

Current Alembic head: `0003_request_gates`

## Purpose

Preserve the first live Phase 3A proof that two BF4PS collectors can concurrently consume one shared bounded detailed/background cohort while PostgreSQL preserves exclusive job ownership and a shared outbound request-gate pacing domain.

This run followed the deterministic concurrent-claim proof and the explicit 403/429 throttle-classification hardening. The live harness was `scripts/phase3a_concurrent_live.py`.

## Safety boundary

The live harness verified before collection:

- database: `bf4_playerstats_test`;
- PostgreSQL writable primary (`pg_is_in_recovery() = false`);
- Alembic revision: `0003_request_gates`;
- detailed/background queue empty;
- frozen collector identities unused;
- exact frozen 12-soldier cohort pristine and `never_attempted`;
- exact platform mix: 4 PC / 4 PS4 / 4 Xbox One;
- feeder target depth: 2;
- hard combined/global collection-attempt ceiling: 12;
- shared egress key: `phase3a-concurrent-tcou`;
- request interval: 2.0 seconds.

No unrestricted backlog consumption was authorized.

## Collector identities

- `phase3a-tcou-a` — UUID `b2b3ef60-62e8-4d4a-91b0-41a2e2a30001`
- `phase3a-tcou-b` — UUID `b2b3ef60-62e8-4d4a-91b0-41a2e2a30002`

Both collectors used the same `background` lane, PostgreSQL database, frozen cohort, and egress key.

## Frozen cohort

PC:

- soldier 20 — `sib181`
- soldier 21 — `Draco1A`
- soldier 22 — `blackcourser`
- soldier 23 — `Nike_Rostov1`

Xbox One:

- soldier 96 — `TheyLuvBubas`
- soldier 97 — `Dannygm1`
- soldier 98 — `BruinZeeSchuim`
- soldier 99 — `SaulShecke`

PlayStation 4:

- soldier 108 — `xXFARLEY98Xx`
- soldier 109 — `m_peinado1`
- soldier 110 — `redm0nk3Y711`
- soldier 111 — `C4_Joe_`

## Live result

The two collectors split the workload exactly 6/6:

- `phase3a-tcou-a`: 6 attempts, 6 successes, 0 failures, 0 throttle signals;
- `phase3a-tcou-b`: 6 attempts, 6 successes, 0 failures, 0 throttle signals.

Combined result:

- 12/12 global attempts consumed;
- 12 successes;
- 0 failures;
- 0 HTTP 403 responses;
- 0 HTTP 429 responses;
- 0 `battlelog_throttle` classifications;
- 12 unique frozen soldiers attempted exactly once;
- all HTTP collection results were 200.

The persisted event ledger recorded this ownership split:

| Event | Collector | Soldier | Platform | Result | HTTP |
|---|---|---:|---|---|---:|
| 35 | phase3a-tcou-a | 20 | pc | success | 200 |
| 36 | phase3a-tcou-b | 21 | pc | success | 200 |
| 37 | phase3a-tcou-a | 22 | pc | success | 200 |
| 38 | phase3a-tcou-b | 23 | pc | success | 200 |
| 39 | phase3a-tcou-a | 96 | xboxone | success | 200 |
| 40 | phase3a-tcou-b | 97 | xboxone | success | 200 |
| 41 | phase3a-tcou-a | 98 | xboxone | success | 200 |
| 42 | phase3a-tcou-b | 99 | xboxone | success | 200 |
| 43 | phase3a-tcou-a | 108 | ps4 | success | 200 |
| 44 | phase3a-tcou-b | 109 | ps4 | success | 200 |
| 45 | phase3a-tcou-a | 110 | ps4 | success | 200 |
| 46 | phase3a-tcou-b | 111 | ps4 | success | 200 |

Every event was attempt 1 with `event_type=collection_success`, `result=success`, and no error class.

## Final validation

Harness assertions all passed:

- exact global 12-attempt ceiling: PASS;
- 12 unique frozen soldiers: PASS;
- shared PostgreSQL request gate exists: PASS;
- both collectors stopped cleanly: PASS;
- operator controls preserved: PASS;
- throttle evidence reconciled between runtime results and persisted events: PASS;
- all collections successful: PASS;
- cohort queue finalized: PASS.

All 12 soldiers finished with `detailed_state=success` and retained detailed current data. The actionable cohort queue was empty at completion.

## Timing observation

The first retained success was at `2026-10-04 07:54:18.776246+00:00` and the final success was at `2026-10-04 07:54:40.330915+00:00`, a span of approximately 21.6 seconds for the 12-success bounded cohort. This is an observation from this run, not a throughput target or authorization to tune request pacing more aggressively.

## Conclusion

Phase 3A live concurrent execution is **PASS**.

The run proves, for this bounded single-host/two-collector test, that both collectors can continuously compete for and process one shared PostgreSQL-backed queue without duplicate logical processing, while obeying the combined attempt boundary and sharing one PostgreSQL request-gate pacing domain. The source side also completed cleanly with no 403/429 throttle evidence.

The retained database rows and events are intentionally left in place as Phase 3A forensic evidence.

Per the frozen Phase 3 implementation order, the next stage is **Phase 3B — deterministic lease expiry, reclamation, and stale-owner fencing**. Phase 3B must retain collector A's stale claim/token, allow collector B to reclaim the same logical job after a deliberately short lease expires, and explicitly prove that A's superseded token cannot perform state-changing ownership operations against B's reclaimed job.
