# BF4PS Phase 3E third endurance run

Status: **LIVE RUN COMPLETE — global reconciliation pending**

Date: 2026-10-04 UTC

Design reference: `docs/phase3e-distributed-endurance-design.md`

Previous evidence: `docs/phase3e-second-endurance-run.md`

Code under test before launch: `3861233`

Current Alembic head: `0003_request_gates`

## Purpose

Round Three was the first live rerun after changing the bounded feeder so its target depth is treated as a replenishment target under concurrent feeders rather than as a hard instantaneous queue-depth invariant.

Round Two demonstrated that three concurrent workers can transiently observe actionable depth 7 while the configured feeder target is 6. The previous implementation raised an exception in that condition. Round Three deliberately exercised the same three-host concurrency after the production feeder patch.

This document records observed worker-console evidence only. Durable database reconciliation remains required before Round Three is declared globally reconciled.

## Frozen workload

Round Three used a new frozen cohort of 120 pristine soldiers:

- 40 PC
- 40 PS4
- 40 Xbox One

The preflight passed before queue seeding.

The initial queue seed created exactly six `detailed/background` pending jobs, jobs 333 through 338, with attempt count zero. The feeder target remained 6 and the hard global attempt ceiling remained 120.

## Physical collectors

The same three physical collectors participated:

- `tcou` / `phase3e-tcou`
- `hnl-01` / `phase3e-hnl-01`
- `kah-01` / `phase3e-kah-01`

Each used its stable collector UUID and dedicated Phase 3E request-gate key. Request interval remained 5 seconds.

## Observed live result

All three workers reached the global attempt ceiling and stopped cleanly.

| Host | Local attempts | Successes | Failures | Max actionable observed | Stop |
|---|---:|---:|---:|---:|---|
| `tcou` | 40 | 40 | 0 | 6 | clean |
| `hnl-01` | 40 | 40 | 0 | 7 | clean |
| `kah-01` | 40 | 40 | 0 | 6 | clean |
| **Total** | **120** | **120** | **0** | **7** | **clean** |

Each worker reported:

- `global terminal: 120/120`
- `actionable now: 0/6`
- `collector stop: PASS`
- `PHASE 3E ENDURANCE WORKER: STOPPED CLEANLY`

## Critical concurrency evidence

`hnl-01` reproduced the exact transient condition that caused the Round Two feeder failure:

```text
NOTICE: transient actionable depth observed above feeder target: 7 > 6
```

The worker did **not** abort. Collection continued normally through local attempt 40, after which the global ceiling was observed and the worker stopped cleanly.

This is the key Round Three result: actionable depth 7 above target 6 is now treated as concurrency telemetry. The feeder refrains from unnecessary replenishment instead of treating the transient observation as a violated global invariant.

Neither `tcou` nor `kah-01` observed a depth above 6 in their local telemetry, while `hnl-01` observed 7. This is consistent with the race being transient and observer-dependent rather than a persistent queue state.

## Source-level result

Worker-console evidence reported:

- 120 local collection attempts in aggregate;
- 120 successes;
- zero failures;
- no visible 403/429/throttle result;
- exact 40/40/40 work distribution across the three physical collectors.

These values are not yet substitutes for durable ledger reconciliation.

## What Round Three proves at the harness level

The live run provides positive evidence that the production feeder patch fixes the Round Two failure mode under real three-host concurrency:

1. multiple workers concurrently consumed and replenished the bounded queue;
2. a transient actionable depth of 7 was reproduced with target 6;
3. that transient depth no longer crashed the feeder;
4. all three workers continued useful work;
5. all three observed the 120-attempt global boundary;
6. all three stopped cleanly;
7. no worker-console collection failure was reported.

## What remains unproven until reconciliation

Round Three is not globally PASS solely from console output. Read-only reconciliation must verify durable database truth, including at minimum:

- exactly 120 terminal Round Three attempt events;
- exact coverage of the frozen Round Three cohort and no soldier outside it;
- no duplicate logical job attempts/finalizations inconsistent with the frozen ceiling;
- attempt accounting consistent with the 120-attempt boundary;
- zero persisted collection failures and zero persisted 403/429/throttle signals for this run;
- correct collector, hostname, and egress snapshots;
- finalized `detailed/background` queue state;
- all three collector rows present and cleanly stopped;
- persistent operator controls preserved;
- all three request-gate rows present;
- Round Three detailed collection state consistent with the event ledger.

The reconciliation must be read-only and perform zero Battlelog requests.

## Phase 3E scope note

Round Three validates sustained concurrent bounded-feeder behavior and the specific Round Two race fix. It does **not by itself** satisfy every frozen Phase 3E lifecycle requirement. The frozen Phase 3E design separately requires deliberate drain/restart/undrain behavior and abrupt owner-loss/reclamation/stale-owner fencing evidence before Phase 3E as a whole can be closed.

## Next step

Build and run a schema-verified, read-only Round Three global reconciliation harness. Preserve its output as evidence before deciding the next Phase 3E lifecycle experiment.
