# BF4PS Phase 4A execution contract

Status: **FROZEN — preflight/run implementation next**

Date: 2026-10-05 UTC

Parent design: `docs/phase4-sustained-collection-ramp.md`

## Purpose

Phase 4A is the first sustained distributed collection run after Phase 3E final acceptance. It intentionally grows `bf4_playerstats_test` using the normal production collection path on three physical nodes.

## Frozen target

- database host: `mak-db-02.bf4statusbot.com`
- database: `bf4_playerstats_test`
- Alembic head: `0003_request_gates`
- resource: `detailed`
- lane: `background`
- cohort: exact frozen 90 PC soldiers in `scripts/phase4a_cohort.py`
- target actionable depth: 6
- maximum terminal attempts: 90 for the initial Phase 4A run
- request spacing: 5.0 seconds per independent egress gate
- lease duration: 120 seconds
- physical collectors: `tcou`, `hnl-01`, `kah-01`

The 90-soldier identity manifest was frozen only after the read-only census and frozen-cohort verifier passed with zero database writes and zero Battlelog requests.

## Production-path rule

Phase 4A collection MUST use the existing production components:

- `bf4ps.bounded_feeder.replenish_detailed_bootstrap`
- collector registration/heartbeat/clean-stop runtime
- normal job claim + lease token ownership/fencing
- PostgreSQL request gates
- `bf4ps.detailed_collector.collect_one_detailed_job`
- normal detailed current/history persistence
- normal collection event ledger/failure handling/finalization

The harness may add safety checks, telemetry and exact cohort boundaries. It must not manufacture successful collection state/current/history/events with direct harness inserts.

## Safety/refusal boundaries

Before any job is created, preflight must refuse unless all of these hold:

1. database/Alembic target is exact and writable primary;
2. the exact 90 frozen soldier/persona/name/platform identities still match;
3. all 90 detailed states are still `never_attempted`;
4. no frozen-cohort detailed job already exists;
5. no detailed/background job exists outside the frozen cohort;
6. no active collector owns a job;
7. the three Phase 3E stable collector identities exist, are enabled, undrained and idle;
8. their egress identities remain exact;
9. required request-gate rows exist;
10. no historical Phase 4A terminal event exists for the frozen cohort.

The worker must continuously enforce the cohort boundary and global attempt ceiling. Any HTTP 403/429 or throttle-class outcome is a stop signal.

## Evidence captured from the beginning

Starting preflight records:

- current/history/event/job counts;
- maximum event ID;
- exact frozen cohort state distribution;
- collector identities/control state;
- request-gate presence/state;
- historical 403/429 counts.

During the run the production bounded feeder is repeatedly invoked with:

- `target_depth=6`
- `max_soldier_id=max(frozen cohort)`
- `allowed_soldier_ids=exact frozen cohort`
- `max_total_attempts=90`

Worker output records local success/failure outcomes and immediately stops on throttle evidence. Final reconciliation will derive durable feeder/queue/event/current/history/per-collector evidence from PostgreSQL plus the captured run output.

## Launch choreography

1. Run Phase 4A preflight on tcou. **No writes / no Battlelog.**
2. If PASS, start the same Phase 4A worker on tcou, hnl-01 and kah-01.
3. Workers register/heartbeat their already-frozen stable collector identities and use distinct request-gate egress keys.
4. Each worker may invoke the transaction-serialized production bounded feeder. The feeder creates only the deficit needed toward actionable depth 6 and only inside the exact cohort.
5. All workers claim and collect through the normal production path until the 90-attempt ceiling/convergence boundary or a stop condition.
6. Stop cleanly and run read-only final reconciliation before declaring Phase 4A PASS.

## Acceptance relationship

This execution contract does not replace `docs/phase4-sustained-collection-ramp.md`. Phase 4A still requires its parent acceptance criteria, including repeated feeder replenishment, participation by all three collectors, reconcilable persistence/event growth, no throttle evidence, no stale ownership and clean final stop.

Phase 4B and 4C remain unauthorized until Phase 4A is reconciled and documented PASS.
