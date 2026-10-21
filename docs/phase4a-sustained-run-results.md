# Phase 4A sustained distributed collection — acceptance record

Status: **PASS**

Date: 2026-10-05/06 UTC

## Purpose

Phase 4A was the first sustained three-node BF4PS detailed-statistics collection run after Phase 3E lifecycle/distributed-worker acceptance. The experiment intentionally changed workload duration/size while retaining the proven production collection path and PostgreSQL-coordinated queue/request-gate design.

The frozen cohort contained exactly 90 previously untouched PC soldiers.

## Frozen execution contract

- Collectors: `phase3e-hnl-01`, `phase3e-kah-01`, `phase3e-tcou`
- Physical hosts: `hnl-01`, `kah-01`, `tcou`
- Resource: `detailed`
- Lane: `background`
- Frozen cohort size: 90 PC soldiers
- Target actionable queue depth: 6
- Global terminal-attempt ceiling: 90
- Per-egress request spacing: 5.0 seconds
- Production detailed collection path used by all three workers
- PostgreSQL request gates used for outbound pacing
- Safety boundary stopped the run on any observed HTTP 403/429 or `battlelog_throttle`

The proven worker implementation was committed as `scripts/phase4a_worker.py` in commit `6aa4daa` (`test: add Phase 4A sustained worker`).

## Preflight

The Phase 4A sustained-run preflight passed before ignition. It established:

- exact frozen identities unchanged;
- all 90 detailed states pristine (`never_attempted`);
- no frozen-cohort detailed jobs existed;
- no foreign detailed/background jobs existed;
- the three stable collectors were exact, enabled, undrained, and idle;
- no active collector owned a job;
- all three required request gates existed;
- no prior Phase 4A terminal events existed; and
- no Battlelog requests or database writes were performed by the preflight.

Starting detailed-stat persistence counters were 797 current rows and 797 history rows. The pre-run collection-event maximum was event 814.

## Sustained run observations

All three workers were launched against the same database and frozen cohort.

Observed local terminal work distribution:

| Collector | Host | Successful terminal attempts |
|---|---|---:|
| `phase3e-hnl-01` | `hnl-01` | 30 |
| `phase3e-kah-01` | `kah-01` | 29 |
| `phase3e-tcou` | `tcou` | 31 |
| **Total** | | **90** |

All workers stopped cleanly after the global terminal-attempt ceiling was reached.

The worker-reported maximum observed actionable queue depth was 6 on tcou, 6 on hnl-01, and 7 on kah-01. The one observed value of 7 is treated as a concurrent/transient observation under multi-worker feeder activity, not evidence of unbounded queue growth. The run converged with zero residual cohort jobs.

## Authoritative post-run database reconciliation

A read-only post-run reconciliation produced the following authoritative result:

- frozen cohort: **90**;
- collection states: **90 `success`**;
- terminal attempts: **90**;
- successes: **90**;
- failures: **0**;
- event span: **815..904**;
- detailed current rows for cohort: **90**;
- detailed history rows for cohort: **90**;
- residual cohort jobs: **0**;
- throttle events: **0**;
- exactly three collectors participated;
- all three collectors owned no current job after completion.

Collector event distribution matched the local worker observations exactly: HNL 30, KAH 29, TCOU 31.

## Acceptance

The post-run verifier reported:

- exactly 90 terminal attempts — **PASS**
- all 90 succeeded — **PASS**
- zero terminal failures — **PASS**
- all 90 detailed states `success` — **PASS**
- 90 current rows persisted — **PASS**
- 90 history rows persisted — **PASS**
- zero residual cohort jobs — **PASS**
- zero throttle events — **PASS**
- exactly three collectors participated — **PASS**
- all collectors own no current job — **PASS**

**PHASE 4A POST-RUN VERIFICATION: PASS**

## Conclusion

Phase 4A demonstrates sustained distributed detailed-stat collection across three physical BF4PS collector hosts using the production queue, lease/fencing, persistence, and PostgreSQL request-gate path. The frozen 90-player workload completed with 100% successful terminal collection, no residual queue work, no observed throttle response, and balanced participation by all three collectors.

This result is the baseline for the next scale step. Phase 4B should use a new deterministic frozen cohort of 900 untouched soldiers so Phase 4A evidence remains immutable and the workload-size increase is isolated as the primary experimental variable.
