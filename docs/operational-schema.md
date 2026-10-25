> **Live production checkpoint — 2026-10-25 UTC:** The `bf4_playerstats` `alembic_version` table was queried directly and returned **`0018_distributed_rank_queue`**. This is the current observed revision, superseding the older 0012/0017 current-revision wording below. The October 21 table/column/index/constraint inventory remains a **dated snapshot**, not a re-count on October 25. No migration was applied in the GitHub-first collector rollout.

> **2026-10-24 operational note (no migration):** `collection_jobs` may retain pending rows for actively excluded soldiers; such rows must be ignored by the claim query, not executed. The `player_exclusions` trigger remains authoritative defense in depth. Fleet pacing changed to 4 seconds per egress; the `runtime_budgets` values remained 4,800/hour. This note does not supersede the dated live schema inventory below.

# Live schema reconciliation — 2026-10-21

**Verified live database:** `bf4_playerstats` on PostgreSQL 16.15, Alembic revision **`0017_rank_immutable_scores`**. The live catalog currently contains **43 public tables, 458 columns, 94 indexes, and 183 constraints**. The complete column/type/default/index/constraint inventory is in [live-schema-snapshot-2026-10-21.md](live-schema-snapshot-2026-10-21.md).

**Important:** The following original schema/design material is retained for historical context; its older migration references are not a claim that the live database is at that revision. Migrations 0014–0017 were absent from the surveyed Git branches but recovered from the deployed `mak-01` collector and added to `player-collector/migrations/versions/`; a clean migration rehearsal is still pending. Do not write schema-dependent code from the historical description without checking the live snapshot and current migrations.

---

# Operational Schema — current entry point

**Current production revision:** `0012_manual_verify_api` (observed 2026-10-17).

For schema-dependent work, consult [database-schema-reference.md](database-schema-reference.md) and the [live 24-table PostgreSQL catalog](LIVE-POSTGRESQL-SCHEMA-2026-10-17.md). Read the applicable Alembic migration files as well. The complete `0005`–`0012` migration source has not yet been located in the inspected checkouts; migration lineage remains unverified.

The previous historical version of this document is retained at [history/pre-0012-operational-schema.md](history/pre-0012-operational-schema.md) and must not be used as the current schema.
