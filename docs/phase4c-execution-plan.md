# Phase 4C — multiplatform sustained collection run

## Purpose

Phase 4C validates the proven distributed detailed-stat collection path against all three BF4 platforms instead of a PC-only cohort.

The frozen cohort is exactly 450 soldiers: 150 `pc`, 150 `ps4`, and 150 `xboxone`. The cohort artifact is `scripts/phase4c_cohort.py` and must not be regenerated after ignition.

## Frozen execution contract

- database: `bf4_playerstats_test`
- writable primary: `mak-db-02.bf4statusbot.com`
- Alembic head: `0003_request_gates`
- resource: `detailed`
- lane: `background`
- cohort: 450 frozen soldiers
- distribution: 150 PC / 150 PS4 / 150 Xbox One
- collectors: `tcou`, `hnl-01`, `kah-01`
- target actionable queue depth: 6
- global terminal-attempt ceiling: 450
- request spacing: 5 seconds per egress gate
- lease: 120 seconds

The harness must use the production bounded feeder and detailed collector. It must not implement a second collection path.

## Preflight acceptance

Before ignition the read-only preflight must prove that the frozen soldier identities are unchanged, the platform distribution is exactly 150/150/150, all 450 detailed collection states are pristine `never_attempted`, no cohort jobs exist, no foreign detailed/background jobs exist, the three frozen collectors are exact/enabled/undrained/idle, no active collector owns a job, all three request gates exist, and the cohort has no prior terminal detailed/background events.

## Runtime safety boundary

Each worker is restricted to the frozen cohort and its frozen collector identity. Runtime must stop rather than expand outside the cohort. A 403, 429, or `battlelog_throttle` signal is a stop condition. The global terminal ledger is capped at 450 attempts.

Normal Battlelog normalization failures are evidence, not automatically infrastructure failures. They remain terminal attempts and are reconciled after the run by platform and error class.

## Post-run acceptance intent

The post-run audit must reconcile the 450 frozen identities by platform, terminal result, collector, persistence, and error class. It must distinguish source-data/normalization outcomes from HTTP throttling and worker/infrastructure failures.

A platform cannot disappear inside an aggregate total. PC, PS4, and Xbox One each require explicit accounting. The run is not accepted merely because the global attempt ceiling is reached.

Required infrastructure invariants include zero 403/429/throttle events, no residual cohort detailed jobs, no foreign detailed/background jobs, no collector left owning a current job, and participation by all three frozen collectors.

## Scope boundary

Phase 4C exercises the `detailed` resource only. It does not collect `profile`, `weapons`, or `vehicles`; those remain separate collection-state resource families and later phases.
