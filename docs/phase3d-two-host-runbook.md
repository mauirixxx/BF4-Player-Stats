# BF4PS Phase 3D three-host distributed proof runbook

Status: **PRE-EXECUTION RUNBOOK — amended and re-frozen before live execution**

Phase 3 design reference: `docs/phase3-distributed-collector-design.md`

Frozen topology: `docs/phase3d-frozen-topology.md`

Current Alembic head: `0003_request_gates`

## Objective

Move the already-proven Phase 3 coordination properties off a single operating system and prove them across three actual BF4PS-capable hosts sharing the same PostgreSQL primary.

The original two-host proof was deliberately expanded before live execution to `tcou`, `hnl-01`, and `kah-01`. Phase 3D remains bounded and does not authorize unrestricted bootstrap collection or a full fleet rollout.

## Entry criteria

The retained Phase 3 evidence must show:

- Phase 3A concurrent execution: PASS
- Phase 3B lease expiry/reclamation/fencing: PASS
- Phase 3C operator lifecycle: PASS
- canonical database schema reference still matches current Alembic head
- all three Phase 3D hosts pass deployment/database preflight appropriate to their role

## Host and egress prerequisites

Use the exact identities and egress mapping frozen in `docs/phase3d-frozen-topology.md`.

`egress_key` models the real Battlelog rate-limit domain, not merely a collector label. The three BF4PS hosts currently have distinct observed public IPv4 egresses and therefore use distinct BF4PS request gates.

`tcou` shares its public egress with BF4 Server Watcher host `mak-01`. BF4PS request-gate coordination does not include BF4SW traffic, so throttle evidence from that egress requires explicit preservation and interpretation.

The initial 3D run keeps conservative request pacing. Rate-limit envelope testing is explicitly later work.

## Frozen workload boundary

The first three-host run uses only:

- resource: `detailed`
- lane: `background`
- BF4PS test database
- one explicit frozen cohort of 36 fresh soldiers
- 12 PC + 12 PS4 + 12 Xbox One
- a hard global attempt/job ceiling of 36 across all three hosts

All three hosts compete for the same shared eligible queue. Do not partition the cohort by platform or host.

Thirty-six jobs are chosen to provide repeated claim/finalize cycles and meaningful overlap across three processes while remaining a bounded correctness experiment. It is not a throughput or Battlelog-limit experiment.

## Required preflight

Before external collection begins, verify read-only:

- database name identifies `bf4_playerstats_test`
- PostgreSQL is writable and not in recovery
- Alembic is `0003_request_gates`
- chosen collector identities do not conflict with unrelated active collectors
- resource/lane are exactly `detailed/background`
- frozen cohort is explicit, pristine, and exactly 12/12/12 by platform
- existing queue state is compatible with the test
- hard global attempt/job ceiling is exactly 36
- work outside the cohort cannot be materialized or claimed
- each host's configured egress key matches its actual egress domain

Preflight performs no Battlelog requests.

## Normal three-host execution sequence

1. Register/start `tcou`, `hnl-01`, and `kah-01` under their frozen stable identities.
2. Materialize only bounded frozen-cohort work.
3. Allow all three hosts to compete for the same PostgreSQL queue.
4. Confirm all three hosts obtain and finalize work while preserving exclusive ownership.
5. Observe collection events and independent request-gate behavior for all three real egress domains.
6. Stop all collectors cleanly at the hard global boundary.
7. Preserve database/event evidence before cleanup if anything unexpected occurs.

## Required normal-run PASS evidence

The normal run must account for all of the following:

- all three physical hosts register as distinct collector identities
- all three hosts claim and successfully finalize at least one job from the same PostgreSQL queue
- no job has duplicate simultaneous ownership
- lease tokens remain unique per claim attempt
- all attempted soldiers remain inside the frozen cohort
- no more than 36 global attempts/jobs occur
- request gates correspond to the three actual BF4PS egress domains
- bounded feeder replenishment remains correct
- final jobs/events/state account for every bounded attempt
- clean collector shutdown clears live current-job ownership as defined by runtime behavior
- operator `enabled`/`drained` state is not silently overwritten
- 403/429/throttle evidence is explicitly reported and reconciled

A Battlelog source failure alone is not automatically a distributed-coordination failure. Source outcome and scheduler/ownership correctness are reported separately.

## Follow-on physical-host lifecycle proof

After the normal 36-job run is preserved/documented, Phase 3D continues with bounded failure/recovery exercises rather than increasing request volume:

1. run a fresh bounded cohort;
2. drain or stop one physical host while the other two remain active;
3. verify survivors continue to claim/finalize work;
4. restart/rejoin the stopped host under the same stable identity and preserved operator controls;
5. deliberately create one abandoned leased job using a deterministic short test lease consistent with Phase 3B semantics;
6. allow another physical host to reclaim the expired logical job;
7. verify the reclaim increments the attempt, rotates the lease token, and stale ownership cannot mutate/finalize the reclaimed job;
8. preserve evidence and stop cleanly.

## Hard failures

Stop and preserve evidence on:

- work outside the frozen cohort
- exceeded global attempt ceiling
- duplicate simultaneous ownership
- stale-owner mutation/finalization succeeding
- collector identity mismatch
- request-gate configuration inconsistent with real egress
- queue corruption
- unexplained event/job/state mismatch

A 403/429 is a source/throttle signal that must be preserved and reported. It is not by itself proof of distributed-coordination failure unless the runtime mishandles it or violates the bounded experiment.

## Database/network policy

All three hosts target the same BF4PS test PostgreSQL primary using `mak-db-02.bf4statusbot.com`. Use the FQDN in BF4PS configuration; do not depend on short-name resolution across sites.

## Safety rule

Three collectors and three BF4PS request gates do not authorize higher per-egress request rates. Phase 3D proves distributed correctness. Battlelog safe-envelope testing and intentional BF4PS/BF4SW coexistence/load testing remain separate later experiments.
