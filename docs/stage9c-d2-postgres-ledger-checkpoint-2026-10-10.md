# Stage 9C D2 — isolated PostgreSQL ledger migration checkpoint (2026-10-10)

**Status:** PASS for isolated schema/migration validation; **NOT** authorization for HTTP dispatch, multi-node activation, or production rollout.

## Target and safety boundary

- Execution host: `tcou`; PostgreSQL server: `mak-db-02.bf4statusbot.com` / `192.168.10.78`.
- Dedicated scratch database: `bf4ps_scratch_stage9c_d2`; dedicated role: `bf4ps_stage9c_d2`; SSL connection.
- Explicit environment: protected `/root/.config/bf4ps/stage9c-d2.env` on `tcou`. No credentials recorded in this document.
- The integration harness `scripts/phase5b_stage9c_d2_ledger_integration.py` requires `--execute`, an exact URL host/database/role match, the expected server IP and writable-primary identity, and an empty public schema before its initial migration.
- The shared T4 scratch database `bf4ps_scratch_stage9c_integration` was not migrated or used; production remains HOLD.

## Actual executed checks

1. Successful authenticated SSL connection to the new D2 database with the expected identity.
2. Alembic upgrade from empty database through `0004_stage9c_supervision_runs`, then to `0005_stage9c_dispatch_ledger`.
3. Asserted head `0005` and presence of `outbound_dispatches`.
4. Inserted one synthetic dispatch row; duplicate logical identity with a distinct primary key correctly raised `IntegrityError`.
5. Downgrade `0005 -> 0004` with nonempty evidence was refused. The row and revision `0005` survived.
6. Removed only the synthetic row, downgraded to `0004`, verified table removal, and upgraded back to `0005`.
7. Harness reported `PASS: D2 isolated 0004->0005, unique identity, guarded downgrade, 0005 restored`.
8. Full offline suite on `tcou`: **535 passed in 1.40s**; git worktree clean at `d5ce27f` before this documentation commit.

## Limits and next tests

- The test validates schema migration and a single-session uniqueness conflict. It does **not** yet prove multi-connection concurrent insertion/admission behavior, transaction lock ordering, collector fencing, or the physical-send rolling-hour cap.
- The unresolved arbitrary pause between durable admission and actual HTTP send remains a hard blocker to asserting **1,296 actual HTTP dispatches per rolling hour**.
- Next: independent-connection concurrency tests on the dedicated D2 database; use synthetic records only, never real HTTP.
- This integration harness expects an initially empty database and is **not rerunnable** against the now-migrated D2 database without a separate, explicitly authorized reset or a new fixture strategy.
