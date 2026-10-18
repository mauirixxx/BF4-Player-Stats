# BF4 Player Stats — current database schema reference

**Observed production revision:** `0012_manual_verify_api` (2026-10-17 23:34 UTC).
**Database:** `bf4_playerstats` · **PostgreSQL:** 16.15 · **Tables:** 24.
**Authoritative live catalog:** [LIVE-POSTGRESQL-SCHEMA-2026-10-17.md](LIVE-POSTGRESQL-SCHEMA-2026-10-17.md).

## Mandatory schema-first development rule

**Query-only work (including website performance optimizations):** read this reference and the dated live catalog, verify the target database revision, and inspect relevant live table/index definitions before changing SQL. The live catalog may serve as the verified structural reference when migration files are unavailable; do not assume it proves intended migration semantics.

**Schema-changing work (DDL, Alembic, or persistence contract changes):** additionally obtain and review the complete applicable Alembic migration chain. If the migration sources cannot be verified, do not make schema changes.

Never infer columns, keys, index definitions or constraints from an older document.

## Current production schema

The linked live catalog is the complete 2026-10-17 read-only inventory of all 24 public tables, their columns, constraints, and indexes. **Use its actual catalog definitions**, not the historical pre-0012 documents. It also records the weapon Top 10 index build and subsequent validation (`indisvalid`, `indisready`, `indislive` all true).

## Migration-source reconciliation — outstanding

The live audit records revision `0012_manual_verify_api`, but the complete migration files `0005` through `0012` were **not present in the inspected website or archived Stage 9C checkouts**. Consequently this documentation does **not** claim to verify the full migration lineage or intended migration semantics. Locate the active collector source checkout and validate its Alembic graph before changing schema-dependent code. Do not synthesize missing migration definitions from live database structure.

## Update procedure for every migration

1. Review the new Alembic migration and its parent revision; confirm the migration chain is complete.
2. Query the target database read-only for `alembic_version`, table definitions, constraints and indexes; verify against the migration source.
3. Regenerate the dated live catalog and update this reference, including the observed revision, date and any known divergence.
4. Commit documentation together with the schema change. Do not label an unverified migration chain as verified.

## Historical documents

The previous `0004_stage9c_supervision_runs`-era references are preserved in [history/](history/) for archaeology only. They are **not** current schema guidance.
