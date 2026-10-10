# Stage 9C D2 — real SQL concurrent admission checkpoint (2026-10-10)

**Operator-reported PASS.** Production HOLD. No real HTTP was dispatched.

Executed on `tcou` against dedicated `bf4ps_scratch_stage9c_d2` (migration `0005_stage9c_dispatch_ledger`):

```text
.venv/bin/python -m scripts.phase5b_stage9c_d2_sql_last_slot_race --execute
PASS: two independent connections, real SQL count, capacity=1, one admitted, one denied
LIMIT: scratch-only capacity=1, no real HTTP or production admission
```

Harness: `scripts/phase5b_stage9c_d2_sql_last_slot_race.py`, introduced in commit `6a71fc2`. The harness uses two independent SQLAlchemy connections, the existing PostgreSQL advisory transaction lock `pg_advisory_xact_lock(hashtext('bf4ps:phase5b-background-service'))`, `clock_timestamp()` sampled after lock acquisition, the real three-source SQL reconciliation query, and synthetic dispatch rows committed by the winning transaction. It checks that the resulting SQL count and synthetic ledger row count equal one. Cleanup targets only the two generated dispatch UUIDs and run-specific egress key.

**What this proves:** a single synthetic capacity slot can be serialized across two concurrent transactions and reflected in subsequent SQL accounting.

**What it does not prove:** the full 1296/hour boundary, collector lease/owner fencing, class fairness, interactive-lane accounting, post-admission send timing, or any guarantee on actual physical HTTP sends. It is not production admission logic. The T4 scratch at `0004` remains untouched.

**Next:** exercise a guarded 1295-of-1296 real-ledger fixture with two contenders (not an arithmetic shortcut), verify SQL accounting and scoped cleanup, then tackle full ownership/fairness and physical-send guarantees separately. Do not enable HTTP or production writes.
