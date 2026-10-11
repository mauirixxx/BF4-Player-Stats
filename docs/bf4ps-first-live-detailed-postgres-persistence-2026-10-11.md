# BF4PS — first live detailed-stat PostgreSQL persistence checkpoint (2026-10-11)

**PASS — one live PC detailed-stat fetch and atomic persistence into isolated Stage 9C integration scratch. Production fleet remains HOLD.**

## Target and preflight

- Execution host: `tcou`, repository checkout `7ac88fd`.
- Database: `bf4ps_scratch_stage9c_integration`, role `bf4ps_stage9c_integration`, writable primary, Alembic `0004_stage9c_supervision_runs`.
- Prior to fixture insertion: `soldiers`, `collectors`, `collection_jobs`, `collection_events`, `detailed_stats_current`, `detailed_stats_history` each had zero rows.
- Full offline regression suite: **800 passed, exit code 0**.
- Existing Phase 1 read-only Battlelog detailed probe succeeded: 191 source general-stat fields, 48/48 normalized retained fields.
- Live persistence target: PC persona `236753552` (`mauirixxx`), one detailed request. No fleet workers enabled.

## Execution

A one-off validation harness on `tcou` used existing BF4PS primitives: `enqueue_job`, `claim_next_job`, `mark_job_running`, `_record_detailed_attempt_started`, `fetch_detailed_stats`, `normalize_detailed_stats`, and `persist_detailed_success`.

The initial attempt failed on the fixture's omitted `soldiers.first_seen_at` / `last_seen_at` NOT NULL values; the fixture transaction rolled back before any live HTTP. The harness was corrected to populate both timestamps. The successful second attempt passed exact database/role/revision/empty-state checks, recorded the attempt-start event, fetched real Battlelog detailed stats, and persisted via the production detailed-success writer.

## Independently queried persisted result

| Check | Observed |
| --- | --- |
| `detailed_stats_current` | 1 |
| `detailed_stats_history` | 1 |
| `collection_jobs` | 0 (finalized) |
| `collection_events` | 2 (`collection_attempt_started`, `collection_success`) |
| `collection_state.detailed_state` | `success` |
| Rank | 140 |
| Kills | 256660 |
| Deaths | 212302 |
| `source_fetched_at` | 2026-10-11 12:39:44.470091 UTC |
| History appended | true |

The database values for kills/deaths matched the freshly normalized live response. The fixture and statistics were **intentionally retained** in the isolated scratch database as evidence; **do not rerun the empty-database-only harness** without designing a separate repeatable cohort path.

## Scope and limitations

- Confirms a real detailed-stat response can be normalized and committed through BF4PS's existing atomic persistence writer, with current/history/state/events/queue finalization consistent.
- This is a manually orchestrated one-off harness, **not** a production service run, complete multi-resource collector pipeline, or distributed live soak.
- It does not establish the global 1296 physical HTTP dispatches per rolling hour, prove all transport retry/redirect behavior, or authorize the full collector fleet.
- The old Phase 2/3 runners pinning Alembic `0003` are historical test artifacts; do not downgrade today's schema to accommodate them.
- Next: implement a repeatable bounded live cohort runner against the documented current schema, validate weapons/vehicles, then expand deliberately with operator-approved request ceilings.
