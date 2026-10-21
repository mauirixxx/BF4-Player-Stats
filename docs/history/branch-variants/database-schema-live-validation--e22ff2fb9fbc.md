# BF4PS database schema live validation

Date: 2026-10-03/04 (Hawaii/UTC validation window)

Branch: `feature/phase2-single-node-loop`

Documented/live Alembic head: `0003_request_gates`

Database: `bf4_playerstats_test`

## Purpose

After two preflight SQL defects exposed assumptions about the database layout, BF4PS established `docs/database-schema-reference.md` as the human-readable schema map and added `scripts/verify_database_schema.py` as a read-only live verifier.

The development rule is now explicit: before writing or modifying SQL, persistence code, integration harnesses, or operational queries, consult the schema reference and current Alembic migrations. Do not infer columns, relationships, timestamps, or row shapes from memory or naming conventions.

## Validation conditions

The verifier was run directly against `bf4_playerstats_test` after the database had reached Alembic revision `0003_request_gates`.

The verifier is read-only and performed no schema changes, data writes, queue operations, collector work, or Battlelog requests.

## Live result

`DATABASE SCHEMA VERIFICATION: PASS`

Validated successfully:

- all documented tables were present;
- no undocumented tables were present;
- the live Alembic revision was exactly `0003_request_gates`;
- every documented application table had the exact expected column set;
- primary-key shapes matched the documented schema;
- required unique keys were present;
- documented foreign keys and delete actions matched;
- the `request_gates` non-empty `egress_key` check was present;
- the detailed-history soldier/observation index was present.

## Critical negative assertions

The live database explicitly confirmed all of the following:

- `collection_state.resource` is absent;
- `detailed_stats_current.observed_at` is absent;
- `detailed_stats_history.source_fetched_at` is absent;
- `detailed_stats_current.gun_master_score` is absent;
- `detailed_stats_history.gun_master_score` is absent.

These assertions protect several important BF4PS schema semantics:

1. `collection_state` is one row per soldier and uses resource-prefixed columns such as `detailed_state` and `detailed_last_success_at`; it is not keyed by a `resource` column.
2. Detailed current and history rows deliberately use different timestamp names: current uses `source_fetched_at`, history uses `observed_at`.
3. Gun Master score is intentionally not retained because live Battlelog validation showed the source field was non-authoritative.

## Development consequence

The schema safety chain is now:

`Alembic migrations -> database-schema-reference.md -> verify_database_schema.py -> application/runtime SQL`

Alembic remains the executable source of truth. The schema reference is the required human-readable map, and the live verifier is a regression guard against documentation/runtime drift.

Every future schema-changing migration must update `docs/database-schema-reference.md` in the same change set. When practical, the verifier should also be updated with any new critical invariant introduced by that migration.

## Phase 2 checkpoint

This validation was completed before resuming the first bounded Phase 2 automatic single-node collection run. The earlier read-only runtime preflight had already confirmed an empty detailed/background queue and exactly three expected bootstrap candidates (`kKaayyyy`, `Strategery`, and `thepoet11`), but automatic collection remained paused until the schema reference was reconciled with the live test database.
