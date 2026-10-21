# BF4PS — Stage 9C D2 three-site, three-hour soak design (2026-10-11)

**Status: preflight design, not yet ignited. Production deployment HOLD.**

## Purpose

Validate the real BF4PS PostgreSQL-backed detailed-statistics collector across three independent sites over a three-hour wall-clock window, exercising shared-queue claiming, bounded Battlelog requests, collector health, pacing, and durable event/state consistency. This is not a performance benchmark or an invitation to expand the cohort.

## Authoritative starting state

Read-only verification on `tcou` before writing this document:
- `bf4ps_scratch_stage9c_d2`, user `bf4ps_stage9c_d2`, writable primary, Alembic `0005_stage9c_dispatch_ledger`.
- Last event ID **109**, 77 collection events, zero outstanding jobs.
- Three enabled, undrained collectors: `tcou`, `kah-01`, `hnl-01`.
- Nine previously verified PC soldiers; retain the existing cohort. Recheck database identity, schema, cohort, and empty queue before ignition.

## Bounded workload proposal

- **Three-hour duration** from a single durable coordinator start time, not three independent host-local starts.
- **Twelve 15-minute rounds** of nine detailed-statistics refresh jobs (one per soldier per round): 108 planned jobs, at most **108 physical Battlelog attempts** in total. This is a *hard global ceiling*, not a per-worker ceiling. A failed attempt consumes one budget slot; do not automatically replace it with an extra HTTP attempt.
- All three workers can claim from the same nine-soldier cohort, without fixed ownership. A per-node safety cap of 36 physical attempts for the full test prevents one site from exhausting the budget if others disappear; uneven distribution within this cap is acceptable.
- Egress gate: **minimum 10 seconds** between requests sharing a site's egress key; PostgreSQL-coordinated reservation. Continue enforcing the existing production background admission budget. HTTP timeout **30 seconds**. Lease **120 seconds**; if waiting for the gate threatens this lease, stop and diagnose instead of silently extending it.
- One scheduler/coordinator alone enqueues each round, only after confirming that no prior-round jobs remain. Do not enqueue the next round into an uncleared queue. On failure, halt future enqueueing and preserve evidence. Never run unbounded worker loops or automatically retry failures.
- Jobs should have explicit run and round attribution via a durable manifest/audit table or operator-owned manifest; do not depend on console logs as the sole source of truth.
- Record event baseline immediately before the first enqueue. Validate cumulative physical attempts from `collection_attempt_started` with `metadata.physical_request=true`; do not use event-ID arithmetic as a count.
- Wall-clock stop at three hours; coordinator must not enqueue afterward. Workers should finish already-owned work only within the agreed grace period, then stop cleanly. A crash must not extend the test duration or request ceiling.

## Preflight and run control

1. Implement a dedicated soak harness and automated tests **against the documented schema**, verifying live schema before code is enabled. Do not reuse the one-shot dynamic trial unchanged: it has a fixed baseline and a three-job-per-worker loop.
2. Create a manifest with run ID, UTC start/deadline, baseline event ID, cohort, per-site UUIDs, round schedule, physical request budget, lease/pacing settings, and paths for logs.
3. Provide separate `preflight`, `prepare`, `coordinator`, `worker`, `status`, `stop`, `verify`, and `cleanup` operations. `preflight`, `status`, and `verify` must be read-only; mutations require `--execute`.
4. Before ignition, validate three hosts, the exact isolated database and role, revision, cohort, collector UUID/egress identities, empty queue, and no other soak running.
5. Collect periodic telemetry: round, elapsed time, job states, lease age, attempts by host, event outcomes, HTTP errors, background admission and egress pacing, per-soldier current/history counts, DB errors, and worker process exit status.
6. Establish a clear stop procedure: prevent new enqueueing, stop workers, let active leases expire or finish, and retain database evidence. Cleanup must never delete non-soak data.

## Pass/fail rules

- 3-hour window completed; 12 rounds admitted (subject to halt-on-failure); no more than 108 real physical attempts and no more than 36 per site.
- Every job claimed/finalized by a valid lease owner; no overlapping accepted success for the same job, no stale success, no duplicate physical attempt ledger entries.
- No unintended requests outside the nine-persona PC cohort; egress gates and production background admission respected.
- All successful detailed fetches update current/state atomically and append history only on actual canonicalized change.
- Zero orphaned or overdue jobs at final audit, and consistent per-soldier current/state/history.
- Any network failures, lease recovery, and load imbalance reported with exact counts. A failure may cause the run to fail; never conceal it by silently increasing the request budget.

## Safety and scope boundaries

The previously verified post-HTTP abandonment recovery used two real HTTP requests for one job; therefore **exactly-once external HTTP is not a guarantee**. Exactly-once accepted database finalization is enforced by lease fencing. No production BF4SW workers or databases, no schema migrations, no additional nodes, no new cohort, and no autonomous open-ended retry loops. Actual three-hour ignition is a separate gated action after the harness is implemented and preflight passes.
