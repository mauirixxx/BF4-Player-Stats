# Live schema reconciliation — 2026-10-21

**Verified live database:** `bf4_playerstats` on PostgreSQL 16.15, Alembic revision **`0017_rank_immutable_scores`**. The live catalog currently contains **43 public tables, 458 columns, 94 indexes, and 183 constraints**. The complete column/type/default/index/constraint inventory is in [live-schema-snapshot-2026-10-21.md](live-schema-snapshot-2026-10-21.md).

**Important:** The following original schema/design material is retained for historical context; its older migration references are not a claim that the live database is at that revision. The versioned migrations for 0014–0017 have not yet been recovered from surveyed Git branches. Do not write schema-dependent code from the historical description without checking the live snapshot and current migrations.

---

# Database Schema — current entry point

**Current production revision:** `0012_manual_verify_api` (observed 2026-10-17).

For schema-dependent work, consult [database-schema-reference.md](database-schema-reference.md) and the [live 24-table PostgreSQL catalog](LIVE-POSTGRESQL-SCHEMA-2026-10-17.md). Read the applicable Alembic migration files as well. The complete `0005`–`0012` migration source has not yet been located in the inspected checkouts; migration lineage remains unverified.

The previous historical version of this document is retained at [history/pre-0012-database-schema.md](history/pre-0012-database-schema.md) and must not be used as the current schema.
