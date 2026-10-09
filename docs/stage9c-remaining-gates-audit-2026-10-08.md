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
