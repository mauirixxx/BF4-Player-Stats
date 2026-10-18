# BF4PS migration recovery tracker (2026-10-18)

## Verified production baseline

- Production `bf4_playerstats` reported Alembic `0012_manual_verify_api` on 2026-10-18 via read-only API database connection.
- The 2026-10-17 catalog in `../LIVE-POSTGRESQL-SCHEMA-2026-10-17.md` captures 24 live tables, columns, constraints, and indexes.
- This live catalog is evidence of *deployed structure*, not proof that all migration scripts are available or reproducible.

## Migration provenance

| Revision | Source evidence | Status |
| --- | --- | --- |
| 0001–0006 | rnt-01 `/opt/bf4-player-stats` Git history and checkout | Present/recoverable; audit chain before release |
| 0007 | Git commit `6989e6f`, `0007_production_physical_dispatch_gate.py` | Recoverable from Git history |
| 0008 | Git commit `23096f6`, `0008_runtime_budgets.py` | Recoverable from Git history |
| 0009 | Git commit `8434897`, `0009_manual_requests.py` | Recoverable from Git history |
| 0010 | Git commit `16d56c1`, `0010_manual_api_function.py` | Recoverable from Git history; declares `down_revision = '0009_manual_requests'` |
| 0011 | Not yet located in inspected local filesystem / available Git refs | Missing source |
| 0012 | Production `alembic_version` = `0012_manual_verify_api`; no script found on tcou | Deployed, source missing |

The commits listed above were inspected in rnt-01 Git history on 2026-10-18. They are provenance pointers, not assertions that those migrations have been replayed against a clean database.

## Recovery procedure and acceptance criteria

1. Search the original BF4 Player Stats Part 8 conversation and any release archives for the **exact** `0011` and `0012` scripts, revision identifiers, parent links, and hashes.
2. Recover the `0001`–`0010` source from Git history into a dedicated recovery branch without touching running collectors or production schema.
3. Check all Alembic `revision` / `down_revision` links, SQL function definitions and database grants against live read-only catalog observations.
4. Run a clean scratch-database migration rehearsal before declaring the chain complete; never run missing-history guesses against production.
5. Keep this tracker and the authoritative schema reference current until the full chain is verified.

## Website optimization dependency

Query-only performance changes may use the verified live catalog. Derived-ranking tables, triggers, and collector persistence changes are schema-changing and must wait for a validated migration chain. The existing public Top 10 cache was deployed at 300 seconds with single-flight request coalescing; it is process-local and not a replacement for indexed ranking data.
