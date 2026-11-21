> **Production topology correction — 2026-11-20 UTC:** BF4PS production now runs on the standalone PostgreSQL 16 primary `bf4ps-db` (`192.168.10.66`). **There is no BF4PS streaming-replica fleet.** The former MAK-DB-02 / MAK-DB-01 / HNL-DB-01 / RNT-DB-01 / KAH-DB-01 topology is retired **for BF4PS**. Those hosts may still run PostgreSQL for other purposes; their health, WAL replay and disk headroom are not BF4PS rollout gates. Historical fleet observations below are dated history, not current deployment instructions. The new primary uses `/fast/pgdata` (observed online with ~761 GB free on 2026-11-20); `/fast/pgfast` is a separate filesystem. Current live Alembic revision must be reverified on `bf4ps-db` before applying 0026; the repository records 0025 as the last confirmed deployed revision and 0026 as proposed. The standalone ranking gate must not be replaced with the obsolete replica-dependent gate.\n\n> **Live production checkpoint — 2026-10-25 UTC:** The `bf4_playerstats` `alembic_version` table was queried directly and returned **`0018_distributed_rank_queue`**. This is the current observed revision, superseding the older 0012/0017 current-revision wording below. The October 21 table/column/index/constraint inventory remains a **dated snapshot**, not a re-count on October 25. No migration was applied in the GitHub-first collector rollout.

> **2026-10-24 collector policy note (no migration):** Active `player_exclusions` entries are matched against `soldiers` by `(platform, persona_id)` in the collection-job candidate query, before claiming work. This prevents excluded pending jobs from repeatedly tripping the existing database safeguard. The rollout did not change schema or moderation policy. The live Alembic revision should be reverified before schema-dependent work; historical revision references below remain dated snapshots.

# Live schema reconciliation — 2026-10-21\n\n**Current schema authority:** `docs/database-schema-reference.md` plus `player-collector/migrations/versions/` and the live `bf4ps-db` catalog. Historical migration checkpoints in this document are not the current deployed revision.\n

**Verified live database:** `bf4_playerstats` on PostgreSQL 16.15, Alembic revision **`0017_rank_immutable_scores`**. The live catalog currently contains **43 public tables, 458 columns, 94 indexes, and 183 constraints**. The complete column/type/default/index/constraint inventory is in [live-schema-snapshot-2026-10-21.md](live-schema-snapshot-2026-10-21.md).

**Important:** The following original schema/design material is retained for historical context; its older migration references are not a claim that the live database is at that revision. Migrations 0014–0017 were absent from the surveyed Git branches but recovered from the deployed `mak-01` collector and added to `player-collector/migrations/versions/`; a clean migration rehearsal is still pending. Do not write schema-dependent code from the historical description without checking the live snapshot and current migrations.

---

# Database Schema — current entry point

**Current production revision:** `0012_manual_verify_api` (observed 2026-10-17).

For schema-dependent work, consult [database-schema-reference.md](database-schema-reference.md) and the [live 24-table PostgreSQL catalog](LIVE-POSTGRESQL-SCHEMA-2026-10-17.md). Read the applicable Alembic migration files as well. The complete `0005`–`0012` migration source has not yet been located in the inspected checkouts; migration lineage remains unverified.

The previous historical version of this document is retained at [history/pre-0012-database-schema.md](history/pre-0012-database-schema.md) and must not be used as the current schema.


## Platoon website retrieval (2026-10-25)

The website reads platoon records directly from PostgreSQL using bounded SELECT-only API queries; the previous monolithic JSON export is retired. The read API accesses `platoons`, `platoon_roster_accounts`, `platoon_roster_personas`, `soldiers`, `detailed_stats_current`, and `platoon_soldier_discovery`. See [PLATOON-READ-API-CUTOVER-20261025.md](PLATOON-READ-API-CUTOVER-20261025.md). This note describes retrieval behavior, not a schema migration.


## Catalog storage maintenance (2026-10-25)

No schema migration. Weapon/vehicle catalogs retain stable IDs and their existing uniqueness constraints. Production catalog write amplification arose from the deployed collector importing an obsolete installed Python package; the correction is deployment/image related, not a table definition change. See [CATALOG-IMPORT-PATH-RECOVERY-20261025.md](CATALOG-IMPORT-PATH-RECOVERY-20261025.md).

### `platoon_manual_refresh` (2026-10-28)

- `platoon_id bigint PRIMARY KEY REFERENCES platoons(platoon_id) ON DELETE CASCADE`
- `last_requested_at timestamptz NOT NULL DEFAULT now()`
- Controlled by `request_platoon_refresh(bigint,boolean)` SECURITY DEFINER function, granted to `bf4ps_stage9c_d2`; see `website/migrations/0019_platoon_manual_refresh.sql`.
