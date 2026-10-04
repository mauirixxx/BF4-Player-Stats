# BF4PS Phase 3E third endurance run

Status: **PASS — live run and durable global reconciliation complete**

Date: 2026-10-04 UTC

Design reference: `docs/phase3e-distributed-endurance-design.md`

Previous evidence: `docs/phase3e-second-endurance-run.md`

Code under test before launch: `3861233`

Reconciliation harness commit: `2e0d50b`

Current Alembic head: `0003_request_gates`

## Purpose

Round Three was the first live rerun after changing the bounded feeder so its target depth is treated as a replenishment target under concurrent feeders rather than as a hard instantaneous queue-depth invariant.

Round Two demonstrated that three concurrent workers can transiently observe actionable depth 7 while the configured feeder target is 6. The previous implementation raised an exception in that condition. Round Three deliberately exercised the same three-host concurrency after the production feeder patch.

Round Three is now closed with both worker-console evidence and durable read-only database reconciliation.

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

## Durable global reconciliation

After all three collectors stopped, `scripts/phase3e_reconcile_round3.py` performed a read-only reconciliation against the BF4PS test PostgreSQL primary. The reconciliation performed zero Battlelog requests and no database mutations.

Observed durable result:

```text
exactly 120 terminal attempt events:             PASS
exactly 120 collection successes:                PASS
zero collection failures:                        PASS
zero 403/429/throttle signals:                   PASS
exactly 120 unique soldiers:                     PASS
exact frozen round-three cohort covered:         PASS
exactly 120 unique logical jobs:                 PASS
attempt numbers all exactly one:                 PASS
all three collectors attempted 40:               PASS
all event snapshots match frozen hosts:          PASS
round-three queue finalized:                     PASS
all three collector rows present:                PASS
all collectors cleanly stopped:                  PASS
operator controls preserved:                     PASS
all three request gates materialized:            PASS
120 detailed states successful:                  PASS
```

Collector distribution reconciled exactly:

| Host | Collector | Durable attempts |
|---|---|---:|
| `hnl-01` | `phase3e-hnl-01` | 40 |
| `kah-01` | `phase3e-kah-01` | 40 |
| `tcou` | `phase3e-tcou` | 40 |

The Round Three queue was empty after finalization. All three request-gate rows were present. All 120 frozen soldiers had successful detailed collection state. No persisted source-level failure or throttle evidence was found.

Final reconciliation result:

```text
BF4PS PHASE 3E ROUND-THREE GLOBAL RECONCILIATION: PASS
```

## Round Three conclusion

Round Three closes the bounded-feeder concurrency defect discovered in Round Two.

The evidence demonstrates that:

1. multiple workers can concurrently consume and replenish the bounded queue;
2. the configured depth of 6 functions as a replenishment target rather than an impossible instantaneous distributed invariant;
3. transient actionable depth 7 is tolerated safely;
4. all three workers continue useful work after that condition;
5. the frozen global attempt ceiling remains exact;
6. no duplicate logical jobs or soldiers appear in durable attempt accounting;
7. the event ledger, collector identity snapshots, request gates, queue convergence, and detailed collection state reconcile cleanly;
8. all three collectors stop cleanly.

No fourth ordinary endurance repetition is required to prove this same feeder property again.

## Phase 3E scope note

Round Three validates sustained concurrent bounded-feeder behavior and the specific Round Two race fix. It does **not by itself** satisfy every frozen Phase 3E lifecycle requirement.

The frozen Phase 3E design still requires deliberate evidence for:

- graceful drain while useful work remains;
- survivor progress while one collector is drained;
- clean restart under the same stable collector identity;
- persistence of the operator `drained` state across restart;
- explicit undrain and safe rejoin;
- abrupt owner loss with an outstanding leased job;
- lease expiration and reclamation by a different physical collector;
- incremented attempt number and rotated lease token on reclamation;
- rejection of stale-owner mark-running, renew, release, and finalize mutations;
- final lifecycle reconciliation.

## Next step

Proceed to a separately staged Phase 3E lifecycle validation. First validate graceful drain/restart/undrain/rejoin. Then validate abrupt owner loss, cross-host lease reclamation, and stale-owner fencing with a deliberately short test lease.
