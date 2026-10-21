# Stage 9C D2 — PostgreSQL SQL/model reconciliation checkpoint (2026-10-10)

**Result:** operator-reported PASS on `tcou` against dedicated D2 scratch database, revision `0005_stage9c_dispatch_ledger`. Production HOLD.

```text
PASS: empty SQL=0 model=0
PASS: three-source-match SQL=1 model=1
PASS: null-event-and-duplicate-start SQL=3 model=3
PASS: reclaim-and-expiry SQL=2 model=2
PASS: D2 three-source SQL/model parity, TEMP fixtures only, no persistent writes
```

Harness: `scripts/phase5b_stage9c_d2_sql_reconciliation.py` (commit `8152aa1`).

## What was verified

The PostgreSQL three-source reconciliation query matched the conservative Python model on four synthetic fixture scenarios. Fixture records were inserted into session-local temporary tables shadowing the real table names. The harness first checked D2 database identity, migration head, and required schema columns. It used the existing background advisory transaction lock and sampled `clock_timestamp()` after acquiring it.

## Limits and next gate

- This is **SQL/model parity on four fixtures**, not exhaustive accounting correctness, real collection-job fairness accounting, or admission authorization.
- It did not validate a full-capacity database budget race or physical HTTP dispatch.
- Next: develop an isolated, guarded **real SQL accounting + concurrent distinct-identity admission** experiment using the same advisory lock. Do not hardcode the 1295 usage baseline; generate controlled synthetic evidence in dedicated D2 scratch and verify cleanup.
- Verify any new query or harness against `docs/database-schema-reference.md` and Alembic migrations before writing persistence SQL.
- The existing T4 scratch remains on `0004`; D2 remains on `0005`. No production migrations, workers, or HTTP permitted.
