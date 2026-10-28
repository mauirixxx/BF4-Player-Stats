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


## Platoon website retrieval (2026-10-25)

The website reads platoon records directly from PostgreSQL using bounded SELECT-only API queries; the previous monolithic JSON export is retired. The read API accesses `platoons`, `platoon_roster_accounts`, `platoon_roster_personas`, `soldiers`, `detailed_stats_current`, and `platoon_soldier_discovery`. See [PLATOON-READ-API-CUTOVER-20261025.md](PLATOON-READ-API-CUTOVER-20261025.md). This note describes retrieval behavior, not a schema migration.


## Catalog storage maintenance (2026-10-25)

No schema migration. Weapon/vehicle catalogs retain stable IDs and their existing uniqueness constraints. Production catalog write amplification arose from the deployed collector importing an obsolete installed Python package; the correction is deployment/image related, not a table definition change. See [CATALOG-IMPORT-PATH-RECOVERY-20261025.md](CATALOG-IMPORT-PATH-RECOVERY-20261025.md).

### Platoon emblem cache operational path (2026-10-27)

`platoons.emblem_path` contains the official Battlelog emblem URL template (`[SIZE]`/`[FORMAT]` placeholders). The website read API uses a deterministic cached local PNG if present, otherwise a default. `bf4ps-platoon-emblem-cache.timer` periodically runs the bounded read-only database reconciler in `website/scripts/cache_platoon_emblems.py` on `tcou`. No database migration or new table is required. Failed downloads use local `.retry` markers with a six-hour cooldown. See `docs/PLATOON-QUEUE-OPERATIONS.md` for deployment and validation.

### Discord platoon preview publishing (2026-10-27, v3 production)

No database migration. On `tcou`, `bf4ps-platoon-emblem-cache.timer` populates official local emblem PNGs; `bf4ps-platoon-preview-images.timer` produces 1200x630 branded cards with proportionally enlarged emblems (up to 495x495, Pillow Lanczos resize), publishing `-v3.png` files; `bf4ps-share-preview-index.timer` reads `platoons` and selects existing v3 assets for the server-rendered Discord OG image. Missing artwork falls back to standard `og-preview.png`. The PHP unfurl handler reads the atomically published JSON index, and platoon OG titles use `BF4 Platoon Stats`. See `docs/PLATOON-QUEUE-OPERATIONS.md` for operational steps.

### Public manual platoon refresh (2026-10-28)

`public.platoon_manual_refresh` holds durable 60-minute per-platoon cooldown timestamps. `public.request_platoon_refresh(bigint,boolean)` is a SECURITY DEFINER scheduling entry point callable only by the website role; it locks the platoon row and advances `platoons.next_refresh_at` without bypassing the collector lease/fencing logic. Gateway-authenticated LAN CIDR clients bypass cooldowns and public rate limits. Migration: `website/migrations/0019_platoon_manual_refresh.sql`; operational details in `docs/PLATOON-QUEUE-OPERATIONS.md`.
