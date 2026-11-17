# General ranking snapshot retention (2026-11-17 UTC)

**Status:** opt-in implementation and one isolated scratch deletion verified. NOT enabled in production; NO timer or fleet scheduling exists.

Implementation: `player-collector/bf4ps/general_rank_retention.py`.

Safety rules:
- Explicit `--execute` required; default no writes.
- Alembic `0026_general_rank_snapshots` required.
- Uses same transaction-scoped advisory lock as publisher (640041, 260026).
- At most ONE completed, unpublished generation deleted per invocation.
- Minimum 60-minute grace (configurable upward with `--min-age-minutes`).
- Two newest completed generations per metric/platform are protected, as is every published generation.
- Deletes parent generation using the migration's `ON DELETE CASCADE` for ranking rows, atomically in one transaction.
- Incomplete generations are not selected for deletion. Those require separate investigation/repair.

Verified on isolated RNT-01 PostgreSQL scratch `bf4ps_rank_scratch` port 5542:
- Invoked once with `--execute` using local postgres account.
- Deleted obsolete generation 1.
- Follow-up: generation 1 absent, zero dangling publication pointers, 56 published scopes still present.
- No production database touched.

**Outstanding:** Measure repeated deletion elapsed time, WAL, disk reuse and replica replay. One-per-run cleanup might not keep up with 56-scope cycles. Avoid creating a timer until observed rates establish a safe cadence. The global advisory lock intentionally serializes publisher and retention and may limit throughput. Check current published pointers, reader MVCC and disk headroom during longer runs. No automatic cleanup is enabled.
