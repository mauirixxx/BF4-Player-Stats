# Stage 9C remaining-gates audit — 2026-10-08

Status: HOLD. This is an evidence reconciliation, not activation approval.

References: docs/stage9c-admission-concurrency-validation.md; docs/stage9c-admission-concurrency-execution-2026-10-08.md; docs/phase5b-stage9c-readiness-review.md; docs/phase5b-stage9c-rolling-budget-boundary-audit.md; docs/database-schema-reference.md.

## Completed evidence — avoid redundant reruns

- Two independent transactions raced the production final-slot admission path at 1295/1296. The losing claim was denied. The corrected-code regression and independent cleanup passed.
- Detailed reservation-to-start transition used the production start writer; aggregate remained 1296 and another claim was denied. Independent cleanup passed.
- Full-ceiling expired unstarted reclaim correction, below-ceiling reclaim, started-lease reclaim and claim-race regression all passed after the correction, with independent cleanup.
- FI-1 rollback, FI-2 start INSERT failure, FI-3 durable start followed by persistence rollback: all passed on isolated scratch, with zero HTTP and independent five-table cleanup.
- Prior scratch rolling-hour boundary, watchdog inspect/main transaction and abort/fallback, and read-only checkpoint contracts passed. These do not prove live ledger completeness or actual host shutdown.

## Bounded remaining technical gates

| Gate | Evidence gap | Next step |
|---|---|---|
| T1 mixed resources and retries | Weapons/vehicles claim contention and detailed start tested, but no complete mixed-resource retry evidence identified | Review production weapons and vehicles start writers; run one focused scratch check only if required |
| T2 duplicate starts | Detailed start writer has no visible duplicate guard; no duplicate invocation test | Review migration constraints and writer; diagnostic no-HTTP scratch check if unresolved |
| T3 persistence failure diagnostics | FI-3 proved committed start survives rollback, not emission of collection_persistence_failure | Trace actual collector exception handling and ledger logging |
| T4 cross-host admission | Two PostgreSQL connections tested on tcou; hnl-01 and kah-01 untouched | Design coordinated zero-HTTP multi-host scratch protocol; operator approval before remote execution |
| T5 physical-start ledger completeness | Scratch rolling-window query correct, live event coverage not established | Design bounded read-only live reconciliation; explicitly report uncertainty |

## Operational readiness gates

- O1: Read-only main test DB revision/schema check; expected Alembic head 0004_stage9c_supervision_runs. Explicit maintenance and rollback authorization required before any migration.
- O2: Actual host-local systemd guard/dependency, DB-loss and lease-expiry stop behavior; dummy-only tests do not prove physical shutdown.
- O3: Independent three-egress collector identity, DB writable primary, no unexpected collectors/materializers, queue/throttle/persistence anomaly and retained retry-debt preflight.
- O4: Fleet emergency stop and rollback procedures, six-hour monitoring checkpoints, and explicit operator authorization for materializer and collector activation.

## Next safe sequence

1. Source/schema audit T1–T3 without DB writes or HTTP.
2. Address only proven missing safety behavior with targeted tests/fixes.
3. Seek operator approval for remote cross-host T4 scratch validation.
4. Resolve T5 and O1–O4 through authorized preflight and operational checks.

Do not change production, run migrations, activate collectors, or send Battlelog requests. Stage 9C HOLD remains in force.

## T1–T3 source review checkpoint (2026-10-08)

Reviewed `scripts/bf4ps_production_collector.py`, `bf4ps/background_service.py`, `bf4ps/detailed_collector.py`, `bf4ps/weapon_collector.py`, and `bf4ps/vehicle_collector.py`.

- Production collector sets `enforce_production_budget=True` for all three resources, and all three collector functions invoke the shared `claim_production_background_job` under that flag. All three write a committed start event before outbound HTTP. This is source-level wiring evidence, not a mixed-resource scratch PASS.
- Weapons and vehicles wrap successful persistence in `try/except Exception`, and on failure attempt a fresh-transaction `collection_persistence_failure` ledger event before re-raising. Failure to write that diagnostic is logged and original exception retained.
- Detailed success persistence currently has no equivalent exception handler or diagnostic-event writer. This is a **confirmed source-level observability gap** relative to the documented collection-event contract. FI-3 did not cover this logging behavior. Design/implement parity and test with no HTTP before trial.
- The detailed start writer inserts without a visible duplicate check. Review actual migration/index constraints and weapons/vehicles start writers before selecting a duplicate-start fix; do not claim a demonstrated duplicate until tested.
- No remote hosts, database writes, or HTTP were used in this source review. Production HOLD.

## Offline validation after detailed diagnostic patch

Operator pulled `31d99aa` on `tcou`; `py_compile bf4ps/detailed_collector.py` succeeded; full offline pytest reported **412 passed in 1.23s**, exit 0. This confirms existing regression compatibility only. It does **not** yet establish that the new detailed `collection_persistence_failure` event commits after a deliberately failed persistence transaction; targeted diagnostic validation remains required. Production Stage 9C remains HOLD.

## Detailed diagnostic scratch checkpoint

Operator executed `scripts.phase5b_stage9c_detailed_diagnostic_scratch --execute` at `e122ed8`: PASS for committed `collection_persistence_failure` after injected persistence rollback, retained physical-start event, rolled-back current/history/state/success, slot 1296 still charged, zero Battlelog requests, exact fixture cleanup, exit 0. **Independent post-run five-table census remains pending.** This harness invokes the production diagnostic helper directly and does not yet exercise the full `collect_one_detailed_job` exception path. T3 remains partially open; production HOLD.

### Independent cleanup — detailed diagnostic harness CLOSED

Operator independently checked the isolated scratch target after diagnostic harness PASS: `collectors=0`, `soldiers=0`, `collection_jobs=0`, `collection_events=0`, `stage9c_supervision_runs=0`; output `PASS: Independent detailed diagnostic cleanup`. The direct diagnostic writer and cleanup subgate is **CLOSED**. Full `collect_one_detailed_job` exception-path integration remains unverified; do not equate the helper invocation with an orchestrator test. Stage 9C HOLD.

### Full detailed collector exception path — scratch PASS, independent census pending

Operator ran `scripts.phase5b_stage9c_detailed_orchestrator_scratch --execute` at `df70d00`: committed diagnostic after injected persistence rollback, physical-start retained, current/history/state/success rolled back, 1296th slot charged, one mocked fetch and **zero real Battlelog requests**, exact fixture cleanup, exit 0. This covers `collect_one_detailed_job` rather than direct helper only. **Independent five-table census and request-gate fixture check still pending**; T3 final closure contingent on independent cleanup. Production Stage 9C HOLD.
