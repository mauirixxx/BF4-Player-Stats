# Stage 9C D2 — last-slot synthetic race checkpoint (2026-10-10)

**Operator result:** PASS on tcou against isolated D2 database `bf4ps_scratch_stage9c_d2` at Alembic `0005`.

```text
.venv/bin/python -m scripts.phase5b_stage9c_d2_last_slot_race --execute
PASS: shared advisory lock, synthetic 1295/1296 baseline, one admitted, one denied
LIMIT: fixture-only budget, not real collector reconciliation or actual HTTP
```

This verifies that two separate connections using `pg_advisory_xact_lock(hashtext('bf4ps:phase5b-background-service'))` serialize a **synthetic** last-slot decision. It does not test the actual collection-event/reservation/dispatch accounting query.

## Next design gate: reconciliation

Consult `docs/database-schema-reference.md`, migrations 0001–0005, `bf4ps/background_service.py`, `bf4ps/dispatch_budget_model.py`, and `docs/stage9c-d2-dispatch-ledger-transaction-contract.md` before implementing SQL.

- Preserve the **existing** advisory lock as the sole background admission authority; sample `clock_timestamp()` after acquiring it.
- Count active started events, unexpired claimed/running reservations, and durable dispatch identities without double counting a logical attempt.
- Verify actual identity joinability: the existing event and job schemas may not carry `resource` and `lease_token` in the same way as the D2 ledger. Do not assume deduplication keys are present; explicitly document any unmatched evidence and conservatively charge it.
- Test timestamp-split cases, lease expiry, reclaims, and concurrent *different* identities at a budget boundary.
- The current pure `unified_rolling_usage` model counts an identity once when any source is active; that is not by itself proof of a hard rolling physical-send bound.
- Arbitrarily late HTTP send remains an unresolved hard blocker for the ≤1296 actual sends per rolling hour requirement.

**Safety:** no T4 upgrade, no production migrations, no collector activation, no HTTP. Production HOLD.
