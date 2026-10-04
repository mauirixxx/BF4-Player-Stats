# BF4PS Phase 3E lifecycle validation plan

Status: **FROZEN implementation input — Lifecycle A first**

Date: 2026-10-04 UTC

Frozen parent design: `docs/phase3e-distributed-endurance-design.md`

Completed endurance evidence: `docs/phase3e-third-endurance-run.md`

Current Alembic head: `0003_request_gates`

## Purpose

The three-host endurance portion of Phase 3E is complete. Round Three reconciled 120/120 successful attempts and closed the bounded-feeder concurrency defect discovered in Round Two.

Phase 3E is not complete because the frozen design also requires deliberate collector lifecycle evidence. This plan separates the remaining work into two experiments so graceful maintenance behavior is not mixed with abrupt ownership-loss behavior.

- **Lifecycle A:** graceful drain, restart while drained, explicit undrain, safe rejoin under a sustained three-host workload.
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

Lifecycle A is deliberately a **larger sustained workload**, not another ordinary 120-player endurance pass. The workload must remain active long enough for the operator to remove and restore a node while the other collectors continue useful work.

## Frozen workload contract

Lifecycle A uses exactly **360 fresh pristine soldiers**:

- **120 PC**
- **120 PS4**
- **120 Xbox One**
- **360 total**

The frozen cohort must contain 360 unique `soldier_id` values and preserve the exact platform assignment selected by the Lifecycle A manifest generator.

The **hard global terminal-attempt ceiling is 360** for Lifecycle A. A soldier may not be substituted dynamically after the cohort is frozen. Work outside the frozen 360 is a hard failure.

The queue remains bounded. The initial queue and subsequent replenishment use the normal **target depth of 6**; the harness must **not materialize all 360 jobs at once**. As established by Phase 3E endurance testing, target depth 6 is a replenishment target, not an instantaneous distributed invariant: a transient concurrent observation above 6 is telemetry rather than failure when caused by concurrent feeders.

The existing generic `phase3e_freeze_manifest.py` remains the 120-soldier 40/40/40 endurance selector and is **not** the Lifecycle A selector. Lifecycle A requires a dedicated selector/frozen cohort implementing this 120/120/120 contract.

## Target collector

Use `hnl-01` as the Lifecycle A drain/restart target unless a preflight condition requires selecting another remote collector **before the run is armed**.

The target must be frozen in the harness before queue seeding. Do not dynamically switch targets after the live experiment begins.

## Required choreography

### A0 — preflight and arm

1. Generate and freeze exactly 360 pristine soldiers matching the 120/120/120 platform contract.
2. Verify every frozen soldier is pristine for detailed collection.
3. Verify all three collector rows exist with the expected stable UUID/name/hostname/egress identity.
4. Verify all three are enabled, not drained, not retired, and own no job before launch.
5. Verify the expected Alembic head and writable BF4PS test primary.
6. Verify no actionable Lifecycle A work already exists before initial seeding.
7. Seed only the bounded initial queue depth of 6.
8. Start all three collectors.

### A1 — establish sustained three-host progress

Before draining anything, require durable evidence that all three physical collectors have completed multiple jobs during this Lifecycle A run and that substantial frozen work remains.

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
6. verify `kah-01` and `tcou` continue useful work during this interval.

A restart that creates a new collector UUID, silently clears `drained`, or permits a claim while still drained is a hard failure.

### A4 — explicit undrain and rejoin

Explicitly set the target collector's persistent drain control back to false.

Require `hnl-01` to subsequently claim and finalize new work under the same stable collector UUID. Survivor workers must remain healthy.

The rejoin proof is not satisfied merely by a heartbeat. At least one post-undrain claim/finalization by the restarted target is required.

### A5 — convergence

Continue until all **360 frozen Lifecycle A soldiers** have reached the experiment's terminal detailed-collection boundary or the hard attempt ceiling forces a stop. Stop all three collectors cleanly and run a read-only global reconciliation before optional cleanup.

## Lifecycle A PASS properties

Lifecycle A passes only if durable evidence demonstrates:

- exactly the frozen 360 soldiers were the authorized workload;
- platform membership is exactly 120 PC / 120 PS4 / 120 Xbox One;
- all work remained inside the frozen cohort;
- the hard global attempt ceiling of 360 was not exceeded;
- the queue was fed through the bounded production feeder rather than pre-materializing 360 jobs;
- all three collectors made useful progress before drain;
- the target drain control became persistent while substantial work remained;
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

- the frozen cohort is not exactly 360 unique soldiers at 120/120/120;
- the drained target claims a new job after drain is effective;
- startup/re-registration silently clears the drain flag;
- collector UUID changes across restart;
- survivor progress stalls for an unexplained distributed-runtime reason;
- work escapes the frozen cohort or 360-attempt ceiling;
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

Before writing or modifying schema-dependent Lifecycle A code, consult `docs/database-schema-reference.md` and the complete current Alembic migration chain. If documentation and migrations disagree, stop and reconcile them before implementation.

## Next implementation step

Build a dedicated read-only Lifecycle A manifest selector for **120/120/120 = 360** pristine soldiers, freeze that exact cohort, then build the preflight and operator choreography around the existing production collector registration, claim, heartbeat, bounded feeder, and finalization paths. The generic 40/40/40 Phase 3E manifest generator must not be reused as the Lifecycle A cohort contract.
