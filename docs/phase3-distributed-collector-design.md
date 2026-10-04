# BF4PS Phase 3 distributed collector design

Status: **FROZEN implementation reference**

Phase 3 begins from the proven Phase 2 checkpoint at commit `8d20763` and current Alembic head `0003_request_gates`.

This document is the implementation reference for Phase 3. Code, harnesses, and operational procedures built for this phase must be checked against this design before implementation. If implementation evidence requires a design change, update and review this document before changing the behavior.

## Purpose

Phase 2 proved the bounded single-node detailed-statistics runtime, including feeder replenishment, collector registration, queue claiming, PostgreSQL request gating, Battlelog collection, persistence, finalization, retry scheduling, mixed-platform operation, and recovery from the retained scheduler incident.

Phase 3 proves that those primitives remain correct when more than one independent collector process operates against the same PostgreSQL queue.

The primary question is:

> Can multiple BF4PS collectors safely share one durable queue and coordinate ownership, leases, request pacing, finalization, operator controls, and recovery without duplicate live ownership or stale-writer corruption?

Phase 3 is a distributed-coordination proof. It is not the full production bootstrap and does not authorize the eight-node fleet to consume the complete BF4PS backlog.

## Existing contracts used by Phase 3

Phase 3 relies on the already-frozen collector architecture and current schema rather than defining a replacement model.

- The durable work unit is one soldier plus one resource.
- `collection_jobs` contains actionable work, not the complete durable backlog.
- A collector normally owns at most one Battlelog resource job at a time.
- `collector_uuid` identifies a durable collector incarnation.
- `lease_token` identifies one specific claim attempt and is the fencing token for state-changing ownership operations.
- PostgreSQL performs atomic job selection/claiming with row locking and `SKIP LOCKED` semantics.
- Expired `claimed` or `running` jobs may be reclaimed.
- Successful finalization requires current unexpired ownership and must not accept a stale lease token.
- Collectors sharing an `egress_key` share one PostgreSQL `request_gates` pacing domain.
- Normal restart/upgrade/reboot preserves collector UUID. Deliberate replacement/re-registration uses a new UUID.
- Operator `enabled` and `drained` controls are authoritative and must not be silently changed by runtime shutdown/restart.

## Schema boundary

Current documented and executable Alembic head is `0003_request_gates`.

Phase 3 design does **not currently require a schema migration**. The current schema already contains the distributed-coordination primitives required for the first proofs: collector UUIDs, live job ownership, unique lease tokens, lease expiry, current collector job identity, event logging, and PostgreSQL-coordinated egress request gates.

Before any Phase 3 SQL, persistence code, integration harness, or operational query is written or modified, implementation must consult:

1. `docs/database-schema-reference.md`;
2. all current Alembic migrations through the current head.

If implementation proves that a schema change is actually required, stop implementation, design the change first, add the next Alembic migration, and update `docs/database-schema-reference.md` in the same change set.

## Resource boundary

Phase 3 distributed-coordination validation uses only the `detailed` resource.

Profile, weapons, and vehicles are intentionally excluded from the initial distributed proof. They introduce different endpoint and persistence behavior but do not need to be present to prove queue ownership, lease fencing, shared pacing, recovery, drain behavior, or multi-host coordination.

## Platform boundary

The validation cohort should include PC, PlayStation 4, and Xbox One soldiers when practical. Phase 2 already established mixed-platform detailed collection, so platform diversity in Phase 3 is intended to prevent the distributed proof from accidentally narrowing that contract.

Platform distribution is not itself the concurrency mechanism and must not be used to partition jobs between collectors. Both collectors must be capable of competing for the same shared eligible queue.

## Safety model

Every live Phase 3 harness must be bounded and fail closed.

At minimum, a live harness must verify before external collection begins:

- target database name identifies the BF4PS test database;
- PostgreSQL is writable and not in recovery;
- Alembic revision is the expected current head;
- the cohort is explicit and frozen for that harness;
- queue state is compatible with the test being performed;
- collector UUIDs and names are the expected test identities;
- resource is `detailed`;
- lane is `background` unless a later explicitly designed test says otherwise;
- maximum attempts/jobs are hard bounded;
- work outside the frozen cohort cannot be materialized or claimed by the harness.

A preflight must not perform Battlelog requests or mutate the queue unless the specific test is explicitly a mutation/setup harness and that mutation is part of the documented proof.

Retained evidence is preferred over automatic cleanup after a meaningful failure. Cleanup must not destroy the state needed to explain an incident.

## Phase 3A — concurrent claim and execution proof

### Objective

Prove that two independent collectors can simultaneously consume one shared bounded queue without duplicate live ownership or duplicate successful processing of the same logical job.

### Initial topology

Run both collectors on `tcou` first. They must have:

- distinct stable `collector_uuid` values;
- distinct collector names;
- the same PostgreSQL database;
- the same `background` lane;
- access to the same frozen cohort and queue;
- the same `egress_key` for the initial proof.

Using one shared egress key is deliberate. It proves that process concurrency does not accidentally multiply Battlelog request rate and that the PostgreSQL request gate coordinates pacing across both processes.

### Cohort

Use a small fresh bounded cohort, initially approximately 12–20 soldiers, with a PC/PS4/Xbox One mix where available. Exact soldier IDs are chosen by a read-only preflight from eligible test data and then frozen into the live proof.

The cohort must be large enough that both collectors have an opportunity to claim work while remaining small enough to inspect every resulting job/event/state transition.

### Required observations

The live proof must establish:

- both collectors register and become operational under their own UUIDs;
- both collectors obtain work during the run when enough work is available;
- no job is simultaneously owned by both collectors;
- each claim has a unique lease token;
- no logical `(soldier_id, detailed)` job produces two concurrent successful ownership paths;
- all attempted work remains inside the frozen cohort;
- combined attempt ceiling is obeyed across both collectors, not independently multiplied by each process;
- shared request-gate pacing is preserved;
- successful jobs finalize and disappear from the actionable queue;
- failed/retryable work follows existing retry semantics rather than being immediately duplicated;
- both collectors stop cleanly with `current_job_id` cleared;
- runtime shutdown does not alter operator `enabled`/`drained` settings.

### Hard failures

Phase 3A fails immediately on evidence of duplicate simultaneous ownership, work outside the cohort, exceeded global attempt ceiling, stale/incorrect collector identity, request-gate bypass, queue corruption, or persistence/finalization inconsistent with lease ownership.

A Battlelog source failure by itself does not necessarily invalidate the concurrency proof if queue ownership, fencing, retry state, and bounded execution remain correct. Source success and scheduler correctness must be reported separately.

## Phase 3B — lease expiry, reclamation, and stale-owner fencing

### Objective

Prove the failure mode the lease token exists to prevent.

Collector A claims a known detailed job. Before normal finalization, A is deliberately interrupted or its progress is otherwise frozen long enough for its lease to expire. Collector B then reclaims the same logical job under a new lease token.

### Required proof

The test must establish:

- A initially owns the job with token A;
- the job is not claimable by B before lease expiry;
- after expiry, B can reclaim it;
- reclamation increments/reflects a new attempt according to current queue semantics;
- B receives token B and token B differs from token A;
- after reclamation, any state-changing operation attempted with A/token A is rejected;
- A cannot mark the reclaimed job running, renew the superseded lease, release B's work, or finalize/delete B's job;
- B can continue/finalize using its current ownership if the source operation succeeds;
- retained events/state make the reclamation understandable operationally.

The test should use a deliberately short test lease rather than waiting for the normal production lease interval. Test-only timing must remain configurable and must not change schema semantics.

### Failure injection rule

Prefer deterministic failure injection in a purpose-built integration harness over timing a manual `kill -9` as the only proof. A later process-kill test may supplement the deterministic test.

The important condition is that the stale `ClaimedJob` object/token from A is retained so fencing can be explicitly challenged after B reclaims the row.

## Phase 3C — drain, stop, and restart behavior under concurrency

### Objective

Prove operator control and persistent collector identity while another collector continues servicing the shared queue.

### Required proof

With A and B both active:

- set one collector drained through the supported control path;
- drained collector accepts no new work;
- any already-owned job is handled according to the runtime's defined graceful-stop behavior rather than abandoned silently;
- the undrained collector continues servicing eligible work;
- stopping/restarting the drained collector does not create a replacement UUID;
- collector name/hostname/egress/lane identity remains consistent;
- operator controls remain preserved rather than reset by registration/startup;
- after explicit undrain/resume, the collector can safely compete for new work again;
- no duplicate claims or stale ownership appear across the transition.

This phase must distinguish a deliberate drain from heartbeat loss or collector failure.

## Phase 3D — two-host distributed proof

### Objective

Repeat the proven coordination behavior across two actual hosts so correctness no longer depends on two processes sharing one operating system.

### Entry criteria

Do not begin 3D until 3A, 3B, and 3C pass on the test database.

### Topology

Use two BF4PS-capable hosts with independent collector UUIDs and shared access to the same PostgreSQL primary.

The first multi-host proof remains bounded to a frozen cohort and detailed/background work. It does not enable unrestricted bootstrap consumption.

The initial two-host run should preserve conservative pacing. Egress configuration must be explicit. If the hosts use independent public egress IPs, they use distinct `egress_key` values; if they actually share an egress IP, they must share one `egress_key`. The key represents the real rate-limit domain, not the collector name.

### Required proof

- both hosts register as distinct collector identities;
- both can concurrently claim from the same PostgreSQL queue;
- queue ownership remains exclusive;
- lease-token fencing remains valid across hosts;
- request pacing corresponds to the configured real egress domains;
- bounded feeder behavior remains correct while collectors consume concurrently;
- stopping or draining one host does not stop the other;
- abandoned work is recoverable after lease expiry;
- final database state and event evidence account for every bounded attempt.

## Feeder ownership during Phase 3

Phase 3 must not allow each collector to independently interpret `max_jobs` as permission to materialize an unbounded multiple of the intended test workload.

The test harness must enforce a **global cohort/attempt boundary** across the concurrent run. Feeder replenishment may occur repeatedly, but materialization and collection must remain inside the frozen cohort and hard global ceiling.

The Phase 2 actionable-depth fix remains part of the contract: delayed retry rows that are not currently claimable must not falsely satisfy immediate working depth and starve other eligible cohort work.

The production architecture may later separate feeder leadership/scheduling from collector execution, but Phase 3 does not require that larger operational decision unless concurrent testing proves the existing feeder invocation model unsafe.

## Request-gate behavior

Request pacing is coordinated by PostgreSQL `request_gates`, keyed by `egress_key`.

For Phase 3A on one host, both collectors intentionally share one egress key. The expected result is serialized/conservatively spaced Battlelog request permission even though queue processing is concurrent.

For Phase 3D, egress keys must model actual network egress. Two independent public IPs may have independent gates; two collectors behind one public IP must not be assigned separate gates merely to increase throughput.

No Phase 3 test is permission to tune Battlelog request intervals aggressively. Throughput optimization comes after distributed correctness.

## Event and evidence requirements

Phase 3 evidence should make it possible to reconstruct:

- which collector claimed each job;
- lease token/attempt identity;
- claim/start/success/failure/retry/reclaim transitions that the current event implementation records;
- source result separately from scheduling result;
- request-gate/HTTP failure evidence where applicable;
- collector state before and after drain/restart/failure tests.

Harness output should include a concise final validation section with explicit PASS/FAIL assertions rather than relying on visual interpretation of logs.

Important live failures are preserved in documentation before cleanup or retry changes are made, following the Phase 2 incident-handling pattern.

## What Phase 3 does not do

Phase 3 does not yet:

- release unrestricted collection against the full discovered population;
- deploy all eight BF4PS background collectors at once;
- implement the dedicated interactive collector lane;
- add profile, weapons, or vehicle distributed collection;
- tune production request rates for maximum throughput;
- finalize active/recent/bootstrap fairness weights;
- finalize bootstrap resource watermarks;
- implement website ETA calculations;
- change the database schema without a separate reviewed design decision.

## Exit criteria

Phase 3 distributed coordination is complete only when all four proof stages have retained evidence and PASS:

1. **3A concurrent execution:** two collectors safely split a shared bounded cohort with no duplicate ownership or boundary violation.
2. **3B lease/fencing:** expired work is reclaimed and a stale owner is demonstrably unable to mutate/finalize the superseded claim.
3. **3C operator lifecycle:** drain/stop/restart preserves identity and control semantics while another collector continues safely.
4. **3D multi-host:** the same coordination properties hold across two actual hosts sharing PostgreSQL.

After these pass, the next design decision is controlled scale-out: increase collector count incrementally, measure per-egress Battlelog behavior and database load, then decide when the eight-node background fleet is safe to enable.

## Implementation order

Implementation follows this document in order:

1. add Phase 3A read-only preflight and deterministic concurrent integration coverage;
2. add bounded Phase 3A live harness;
3. preserve results before proceeding;
4. build deterministic Phase 3B fencing/reclamation proof;
5. preserve results;
6. build Phase 3C drain/restart proof;
7. preserve results;
8. prepare and execute bounded two-host Phase 3D proof;
9. write final Phase 3 validation record before any broader rollout.

**Frozen rule:** correctness first, bounded live evidence second, scale third.