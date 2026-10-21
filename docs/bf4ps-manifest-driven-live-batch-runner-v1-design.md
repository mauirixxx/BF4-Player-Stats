# BF4PS — manifest-driven live batch runner, v1 design

Status: **implementation reference**. Do not activate the production distributed fleet.

## Purpose

Replace one-off Stage 9C scripts with a reusable, restart-safe runner for a known cohort of soldiers and an explicit resource set, backed by the existing PostgreSQL job queue, collector admission, request gates, and persistence writers.

## Manifest contract

A local JSON manifest (version 1) records `run_id`, expected database/role/revision, collector UUID and egress key, soldier identities (platform/persona/name), resource list, max physical attempts, request interval, and a durable starting event ID. The manifest must be written **before** any jobs are queued. The manifest path and run ID are immutable after initialization.

A new invocation always loads and verifies the same manifest; it never resets the event baseline, never increases the attempt ceiling implicitly, and never widens the cohort. Run reports derive from database events and rows, not from process-local counters.

## Commands

- `preflight`: read-only, show DB identity, existing soldier identities, resource state, current queue, collector state, planned jobs and estimated request volume. No HTTP and no writes.
- `init`: with explicit approval flag, persist a new manifest atomically and idempotently insert any missing soldier identities, using the documented schema. Must reject an existing conflicting manifest.
- `run`: enqueue only missing requested resource work, using the queue's unique soldier/resource constraint. Resume from the same manifest and baseline. Execute through the real resource collector with `allowed_soldier_ids`, `max_total_attempts`, `attempts_after_event_id`, `attempt_ceiling_resources` and `enforce_production_budget=True`. Stop on any failure or inability to claim work.
- `verify`: read-only report of every requested soldier/resource, latest state, current rows, history if applicable, durable events, pending jobs and attempts consumed.

## Crash/restart invariants

1. A crash before a network request must not reset a global attempt cap. Existing durable queue claims and attempt-start/terminal events remain the source of truth.
2. A crash after a request but before a success event must not silently issue an unaccounted retry. If the durable ledger cannot prove whether a physical attempt occurred, stop for operator inspection; do not assume it did not.
3. Repeated `run` never queues already-successful resources unless the operator explicitly starts a new, separately bounded refresh run.
4. An existing queue job owned by another run/collector must not be stolen or re-prioritized.
5. `verify` is safe at any time, including after interrupted runs.

## Test plan

Offline unit tests for manifest parsing, duplicate identities, supported resources, immutable baseline, budget exhaustion, no-op resume and failure-stop. Integration tests on a fresh isolated DB at the documented revision. Only then a bounded live five-soldier weapons+vehicles batch; production remains HOLD.

## Scope control

No gateway/firewall changes, no BF4SW modifications, no migration merely to support a test harness. Existing Stage 9C scratch DB currently at `0004_stage9c_supervision_runs` and retains eight live detailed soldiers, with three having weapons and vehicles. Existing documented head is `0005_stage9c_dispatch_ledger`; verify live schema before any SQL.
