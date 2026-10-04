# BF4PS Phase 3E lifecycle validation plan

Status: **STAGED implementation input — Lifecycle A first**

Date: 2026-10-04 UTC

Frozen parent design: `docs/phase3e-distributed-endurance-design.md`

Completed endurance evidence: `docs/phase3e-third-endurance-run.md`

Current Alembic head: `0003_request_gates`

## Purpose

The three-host endurance portion of Phase 3E is complete. Round Three reconciled 120/120 successful attempts and closed the bounded-feeder concurrency defect discovered in Round Two.

Phase 3E is not complete because the frozen design also requires deliberate collector lifecycle evidence. This plan separates the remaining work into two experiments so graceful maintenance behavior is not mixed with abrupt ownership-loss behavior.

- **Lifecycle A:** graceful drain, restart while drained, explicit undrain, safe rejoin.
- **Lifecycle B:** abrupt owner loss, lease expiration, cross-host reclamation, stale-owner fencing.

Lifecycle A is implemented and executed first. Lifecycle B is designed in detail only after Lifecycle A evidence is reconciled.

## Safety boundary shared by both experiments

All lifecycle validation remains restricted to:

- database: `bf4_playerstats_test`
- PostgreSQL target: `mak-db-02.bf4statusbot.com`
- resource: `detailed`
- lane: `background`
- explicit fresh frozen cohort only
- bounded feeder only
- explicit hard global attempt ceiling
- conservative per-egress pacing

No full-population bootstrap is authorized. No production BF4PS database is authorized. No intentional Battlelog throttle experiment is authorized.

Every harness must refuse to run if the database target, Alembic head, frozen cohort, or expected collector identity does not match its frozen configuration.

## Stable physical identities

The lifecycle tests continue to use:

| Physical host | Collector | Stable UUID | Egress key |
|---|---|---|---|
| `hnl-01` | `phase3e-hnl-01` | `b2b3ef60-62e8-4d4a-91b0-41a2e2a3e001` | `phase3e-hnl-01` |
| `kah-01` | `phase3e-kah-01` | `b2b3ef60-62e8-4d4a-91b0-41a2e2a3e002` | `phase3e-kah-01` |
| `tcou` | `phase3e-tcou` | `b2b3ef60-62e8-4d4a-91b0-41a2e2a3e003` | `phase3e-tcou` |

Stable collector identity must survive restart. Persistent operator controls must not be silently reset by registration or startup.

# Lifecycle A — graceful drain/restart/rejoin

## Objective

Prove that one physical collector can be removed from active claiming while useful work remains, restarted under the same stable identity without losing its persistent drain state, explicitly returned to service, and resume useful work while the other two collectors continue uninterrupted.

## Target collector

Use `hnl-01` as the Lifecycle A drain/restart target unless a preflight condition requires selecting another remote collector before the run is armed.

The target must be frozen in the harness before queue seeding. Do not dynamically switch targets after the live experiment begins.

## Workload sizing

Lifecycle A requires a fresh mixed-platform cohort large enough that useful work remains throughout drain, restart, and rejoin.

The exact cohort and global ceiling are selected by the read-only manifest/preflight immediately before implementation. The run must remain explicitly bounded. The queue target remains a replenishment target rather than an instantaneous distributed invariant.

The test should not consume the entire workload before the operator can complete the lifecycle sequence. If necessary, use a larger frozen cohort or slower conservative pacing; do not create artificial unbounded work.

## Required choreography

### A0 — preflight and arm

1. Freeze a fresh mixed-platform cohort.
2. Verify every frozen soldier is pristine for detailed collection.
3. Verify all three collector rows exist with the expected stable UUID/name/hostname/egress identity.
4. Verify all three are enabled, not drained, not retired, and own no job before launch.
5. Verify the expected Alembic head and writable BF4PS test primary.
6. Seed only the bounded initial queue depth.
7. Start all three collectors.

### A1 — establish sustained three-host progress

Before draining anything, require durable evidence that all three physical collectors have completed multiple jobs during this lifecycle run.

Do not trigger the drain immediately after startup. The point is to demonstrate a running distributed workload, not merely registration.

### A2 — persistently drain `hnl-01`

Set the existing persistent `collectors.drained` operator control for the frozen target collector.

After the drain becomes visible to the worker:

- `hnl-01` must claim no new job;
- if it already owns a job, that ownership may finish normally;
- `kah-01` and `tcou` must continue claiming/finalizing work;
- bounded feeder progress must continue;
- the target collector row must remain `drained = true`.

Record the durable event boundary around the drain so reconciliation can distinguish work claimed before the drain from any forbidden new ownership afterward.

### A3 — clean stop and restart while drained

Once the drained target has no current job:

1. stop the `hnl-01` lifecycle worker cleanly;
2. verify its stable collector row still has `drained = true`;
3. restart the worker using the same stable collector UUID;
4. verify registration/startup does not clear the persistent drain control;
5. leave it running while drained long enough to demonstrate that it claims no work;
6. verify the two survivors continue useful work during this interval.

A restart that creates a new collector UUID, silently clears `drained`, or permits a claim while still drained is a hard failure.

### A4 — explicit undrain and rejoin

Explicitly set the target collector's persistent drain control back to false.

Require `hnl-01` to subsequently claim and finalize new work under the same stable collector UUID. Survivor workers must remain healthy.

The rejoin proof is not satisfied merely by a heartbeat. At least one post-undrain claim/finalization by the restarted target is required.

### A5 — convergence

Continue until the frozen Lifecycle A completion boundary is reached. Stop all three collectors cleanly and run a read-only global reconciliation before optional cleanup.

## Lifecycle A PASS properties

Lifecycle A passes only if durable evidence demonstrates:

- all work remained inside the frozen cohort;
- the hard global attempt ceiling was not exceeded;
- all three collectors made useful progress before drain;
- the target drain control became persistent while work remained;
- no new target ownership began after the drain became effective;
- any pre-existing target ownership finalized normally;
- the two surviving collectors continued progress during drain and restart;
- restart used the same stable collector UUID;
- restart did not clear `drained = true`;
- the restarted-but-drained collector claimed no work;
- explicit undrain changed the persistent control intentionally;
- the target subsequently claimed and finalized new work;
- event identity snapshots remained attributable to the correct physical hosts;
- request-gate identity remained correct;
- final queue/event/state accounting reconciled;
- all collectors stopped cleanly.

## Lifecycle A hard stops

Immediately stop new work and preserve evidence if:

- the drained target claims a new job after drain is effective;
- startup/re-registration silently clears the drain flag;
- collector UUID changes across restart;
- survivor progress stalls for an unexplained distributed-runtime reason;
- work escapes the frozen cohort or attempt ceiling;
- queue/event/state accounting diverges;
- request-gate identity changes unexpectedly.

# Lifecycle B — abrupt owner loss/reclamation/fencing

Lifecycle B remains required but is intentionally not combined with Lifecycle A.

Its frozen parent requirements are:

1. arrange one bounded test job to be owned under a deliberately short test lease;
2. terminate that owner without graceful release/finalization;
3. prove survivors continue unrelated work;
4. wait for lease expiration;
5. require a different physical collector to reclaim the same logical job;
6. prove attempt number increments and lease token rotates;
7. attempt stale-owner mark-running, renew, release, and finalize mutations using the former ownership tuple and require rejection;
8. allow only the current owner to finalize normally;
9. reconcile the complete durable ownership/event history.

The short lease is test-only and must not redefine normal production lease duration.

Lifecycle B implementation is deferred until Lifecycle A passes, because the owner-loss harness must be designed around the exact production ownership/fencing APIs rather than ad-hoc SQL mutations.

## Implementation rule

Lifecycle harnesses must use production collector/queue ownership APIs wherever the behavior under test is a production invariant. Direct SQL is acceptable for read-only validation and explicit operator-control setup only where the production design defines that field as persistent operator state. Harnesses must not invent a second scheduler, ownership model, or cleanup path.

## Next implementation step

Build the Lifecycle A preflight and operator choreography around the existing production collector registration, claim, heartbeat, bounded feeder, and finalization paths. Before writing those harnesses, inspect those production modules directly and keep every schema-dependent query aligned with `docs/database-schema-reference.md` and the current Alembic migration chain.
