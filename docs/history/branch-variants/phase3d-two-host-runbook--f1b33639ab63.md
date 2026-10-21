# BF4PS Phase 3D two-host distributed proof runbook

Status: **PRE-EXECUTION RUNBOOK — derived from frozen Phase 3 design**

Phase 3 design reference: `docs/phase3-distributed-collector-design.md`

Current Alembic head: `0003_request_gates`

## Objective

Move the already-proven Phase 3 coordination properties off a single operating system and prove them across two actual BF4PS-capable hosts sharing the same PostgreSQL primary.

Phase 3D remains a bounded validation. It does not authorize unrestricted bootstrap collection or an eight-node rollout.

## Entry criteria

The retained Phase 3 evidence must show:

- Phase 3A concurrent execution: PASS
- Phase 3B lease expiry/reclamation/fencing: PASS
- Phase 3C operator lifecycle: PASS
- canonical database schema reference still matches current Alembic head

## Host prerequisites

Before choosing the frozen cohort or making any queue mutation, identify two actual BF4PS-capable hosts and record for each:

- hostname
- stable collector UUID
- collector name
- lane (`background`)
- PostgreSQL connection target
- real public egress/rate-limit domain
- resulting `egress_key`

Collector UUIDs must be distinct and stable. Collector names must be distinct.

## Egress rule

`egress_key` models the real Battlelog rate-limit domain, not a host or collector label.

- If the two hosts use different public egress IPs, use distinct egress keys.
- If the two hosts actually share one public egress IP, use the same egress key.

Do not manufacture separate egress keys merely to increase request throughput.

The initial 3D run keeps conservative request pacing. Rate-limit envelope testing is explicitly later work.

## Frozen workload boundary

The first two-host run uses only:

- resource: `detailed`
- lane: `background`
- BF4PS test database
- one explicit frozen cohort
- a hard global attempt/job ceiling across both hosts

Prefer a fresh mixed-platform cohort containing PC, PS4, and Xbox One soldiers where eligible data permits.

Both hosts compete for the same shared eligible queue. Do not partition the cohort by platform or host.

## Required preflight

Before external collection begins, verify read-only:

- database name identifies `bf4_playerstats_test`
- PostgreSQL is writable and not in recovery
- Alembic is `0003_request_gates`
- chosen collector identities do not conflict with unrelated active collectors
- resource/lane are exactly `detailed/background`
- frozen cohort is explicit and pristine for the proof
- existing queue state is compatible with the test
- global attempt/job ceiling is explicit
- work outside the cohort cannot be materialized or claimed
- each host's configured egress key matches its actual egress domain

Preflight performs no Battlelog requests.

## Execution sequence

1. Start/register host A and host B under their frozen stable identities.
2. Materialize only bounded frozen-cohort work.
3. Allow both hosts to compete for the same PostgreSQL queue.
4. Confirm both hosts obtain work while preserving exclusive ownership.
5. Observe collection events and request-gate behavior for the real egress configuration.
6. Drain or stop one host while the other remains active; verify the survivor continues.
7. Include a controlled abandoned-work/recovery exercise using a deliberately short test lease or other deterministic method already consistent with Phase 3B semantics.
8. Verify the surviving/second host can reclaim expired work under a new lease token and stale ownership cannot mutate the reclaimed job.
9. Stop both collectors cleanly after the hard global boundary is reached.
10. Preserve database/event evidence before cleanup if anything unexpected occurs.

## Required PASS evidence

The final validation must account for all of the following:

- both physical hosts register as distinct collector identities
- both hosts claim work from the same PostgreSQL queue
- no job has duplicate simultaneous ownership
- lease tokens remain unique per claim attempt
- stale-owner fencing remains valid across hosts
- all attempted soldiers remain inside the frozen cohort
- hard global attempt/job ceiling is obeyed
- request gates correspond to actual egress domains
- bounded feeder replenishment remains correct
- draining/stopping one host does not stop the other
- abandoned work becomes recoverable after lease expiry
- reclaimed work receives current ownership/new lease token semantics
- final jobs/events/state account for every bounded attempt
- clean collector shutdown clears live current-job ownership as defined by runtime behavior
- operator `enabled`/`drained` state is not silently overwritten

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

A Battlelog source failure alone is not automatically a distributed-coordination failure. Report source outcome separately from scheduler/ownership correctness, as in Phase 3A.

## Information required before building the host-specific harness

The frozen Phase 3 design intentionally does not invent deployment details. Before implementation of the actual 3D harness, record:

1. the two hosts to use;
2. their stable collector UUIDs/names, or the approved method for creating those identities;
3. whether their real public Battlelog egress is shared or independent;
4. how the same BF4PS repository/virtualenv/runtime will be made available on both hosts;
5. how both hosts reach the same `bf4_playerstats_test` PostgreSQL primary.

Once those facts are known, build the host-specific preflight/harness against this runbook rather than guessing infrastructure values.
