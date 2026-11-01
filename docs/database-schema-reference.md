# BF4 Player Stats database schema reference

Status: **developer reference for the current Alembic head**

Current production Alembic head: `0019_soldier_search_trigrams` (2026-10-31 search-index deployment). Operator verified directly on current primary **MAK-DB-02** on 2026-10-22 with `sudo -u postgres psql -d bf4_playerstats -Atc "SELECT version_num FROM alembic_version;"`. The previous `0017_rank_immutable_scores` observation on 2026-10-21 remains historical; see `live-schema-snapshot-2026-10-21.md` for that earlier catalog. PostgreSQL primary is an HA role and may change during failover.

## Mandatory SQL development rule

**Before writing or modifying SQL, persistence code, integration harnesses, or operational queries, consult this document AND the current Alembic migrations. Never infer a table, column, relationship, timestamp name, or row shape from memory or naming conventions.**

The Alembic migration chain remains the executable source of truth. This document is the human-readable map. If they disagree, stop and reconcile the documentation before continuing implementation.

For live validation, PostgreSQL introspection (`information_schema`, `pg_catalog`, or SQLAlchemy `inspect()`) may additionally be used to confirm that the target database is actually at the expected migration revision.

## Migration chain

| Revision | Parent | Change |
|---|---|---|
| `0001_initial_schema` | base | Initial BF4PS schema |
| `0002_drop_gun_master_score` | `0001_initial_schema` | Removes non-authoritative `gun_master_score` from detailed current/history |
| `0003_request_gates` | `0002_drop_gun_master_score` | Adds PostgreSQL-coordinated outbound request gates |
| `0004_stage9c_supervision_runs` | `0003_request_gates` | Adds inert Stage 9C watchdog run/lease state (no data backfill or activation) |
| `0005_stage9c_dispatch_ledger` | `0004_stage9c_supervision_runs` | Adds durable outbound dispatch ledger |
| `0006_stage9c_soak_round_ledger` | `0005_stage9c_dispatch_ledger` | Adds Stage 9C soak run/round/job ledgers; originally designated scratch-only, but production was independently observed at this revision on 2026-10-14 UTC |
| `0007_physical_dispatch_gate` | `0006_stage9c_soak_round_ledger` | Adds request ordinal and physical-request uniqueness to outbound dispatches; does not activate collection |
| `0008_runtime_budgets` | `0007_physical_dispatch_gate` | Fleet physical dispatch and background admission ceilings |
| `0009_manual_requests` | `0008_runtime_budgets` | Inert manual request ledger and cooldown anchors; no website role or public API |
| `0010_manual_api_function` | `0009_manual_requests` | Restricted manual-request SQL API |
| `0011_manual_verification` | `0010_manual_api_function` | Pending Battlelog soldier verification |
| `0012_manual_verify_api` | `0011_manual_verification` | Restricted verification request SQL API |
| `0013_indexed_equipment_rankings` | `0012_manual_verify_api` | Indexed weapon and vehicle leaderboard read models |
| `0014_equipment_populations` | `0013_indexed_equipment_rankings` | Equipment population data |
| `0015_rank_generations` | `0014_equipment_populations` | Rank generation state |
| `0016_rank_scope_versions` | `0015_rank_generations` | Rank scope versions |
| `0017_rank_immutable_scores` | `0016_rank_scope_versions` | Immutable rank score snapshots |
| `0018_distributed_rank_queue` | `0017_rank_immutable_scores` | Adds durable equipment ranking jobs, worker registry, and single-row global ranking capacity |
| `0019_soldier_search_trigrams` | `0018_distributed_rank_queue` | Adds pg_trgm and concurrent GIN lower(name) indexes for soldier current and historical substring search |

### Important migration consequence: Gun Master

`gun_master_score` existed in the initial migration but **does not exist at the current head**. Live Battlelog validation showed the source field remained zero for players known to play and win Gun Master rounds, so BF4PS intentionally does not retain it.

## Global domain values

- Platforms: `pc`, `ps4`, `xboxone`
- Resources: `detailed`, `profile`, `weapons`, `vehicles`
- Collection states: `never_attempted`, `success`, `temporary_failure`, `unavailable`
- Collector lanes: `background`, `interactive`
- Job priority classes: `interactive`, `active`, `recent`, `bootstrap`
- Job statuses: `pending`, `claimed`, `running`

**Collection-state spelling is schema-significant.** The pristine/unattempted value is exactly `never_attempted`; `never` is not a legal collection-state value. Harnesses and operational SQL must use the exact domain values above rather than abbreviated or remembered spellings.

## Core identity and discovery tables

### `soldiers`

One row per BF4 soldier identity per platform.

| Column | Notes |
|---|---|
| `soldier_id` | bigint identity PK |
| `persona_id` | bigint, required |
| `platform` | required; `pc`/`ps4`/`xboxone` |
| `current_name` | required, non-empty |
| `first_seen_at` | timestamptz |
| `last_seen_at` | timestamptz |
| `created_at` | timestamptz |
| `updated_at` | timestamptz |

Unique: (`persona_id`, `platform`).

### `soldier_sources`

Composite PK: (`soldier_id`, `source_type`). `soldier_id` -> `soldiers` CASCADE. Source types: `bf4sw`, `manual`.

Columns: `soldier_id`, `source_type`, `first_seen_at`, `last_seen_at`.

### `soldier_names`

Historical/observed names for a soldier.

Columns: `soldier_name_id` PK, `soldier_id` FK CASCADE, `name`, `first_seen_at`, `last_seen_at`.

Unique: (`soldier_id`, `name`).

Search acceleration: `pg_trgm` GIN expression indexes on `lower(soldiers.current_name)` and `lower(soldier_names.name)` support `LIKE '%term%'` queries. Built concurrently to avoid long exclusive table locks.

### `battlelog_profiles`

Columns: `profile_id` PK, `battlelog_username`, `battlelog_user_id`, `country_code`, `country_name`, `access_state`, `last_checked_at`, `last_success_at`, `last_error`, `created_at`, `updated_at`.

`access_state`: `public_country`, `public_no_country`, `friends_only`, `not_found`, `error`.

Battlelog username is uniquely indexed case-insensitively.

### `profile_soldiers`

Many-to-many link between Battlelog profiles and soldiers.

Composite PK: (`profile_id`, `soldier_id`). Also contains `first_seen_at`, `last_seen_at`.

## Detailed statistics

### `detailed_stats_current`

Exactly one current detailed-stat row per soldier (`soldier_id` is PK/FK CASCADE).

**Timestamp semantics:** this table uses `source_fetched_at`. It does **not** have `observed_at`.

Metadata columns:

- `soldier_id`
- `source_fetched_at`
- `updated_at`

Retained detailed fields at current head (48):

`rank`, `time_played_seconds`, `assault_score`, `engineer_score`, `support_score`, `recon_score`, `commander_score`, `squad_score`, `vehicle_score`, `award_score`, `unlock_score`, `total_score`, `combat_score`, `conquest_score`, `rush_score`, `team_deathmatch_score`, `domination_score`, `obliteration_score`, `defuse_score`, `capture_the_flag_score`, `air_superiority_score`, `carrier_assault_score`, `chain_link_score`, `kills`, `deaths`, `kill_assists`, `wins`, `losses`, `shots_fired`, `shots_hit`, `repairs`, `revives`, `heals`, `resupplies`, `avenger_kills`, `savior_kills`, `suppression_assists`, `quit_percentage`, `flags_captured`, `flags_defended`, `dogtags_taken`, `vehicles_destroyed`, `vehicle_damage`, `headshots`, `longest_headshot`, `highest_kill_streak`, `nemesis_kills`, `highest_nemesis_streak`.

All retained statistic fields are nullable. Most are bigint. `quit_percentage` is numeric(10,6); `longest_headshot` is numeric(14,4).

### `detailed_stats_history`

Append-on-change detailed snapshots.

**Timestamp semantics:** this table uses `observed_at`. It does **not** have `source_fetched_at`.

Columns: `snapshot_id` PK, `soldier_id` FK CASCADE, the same 48 retained detailed fields as current, and `observed_at`.

Index: (`soldier_id`, `observed_at DESC`).

## Weapon and vehicle tables

### `weapon_catalog`

Columns: `weapon_id` PK, unique `weapon_guid`, `name`, `slug`, `category`, `first_seen_at`, `last_seen_at`.

### `soldier_weapon_stats`

Composite PK: (`soldier_id`, `weapon_id`).

Columns: `soldier_id`, `weapon_id`, `kills`, `headshots`, `shots_fired`, `shots_hit`, `time_equipped_seconds`, `source_fetched_at`, `updated_at`.

### `vehicle_catalog`

Columns: `vehicle_id` PK, unique `vehicle_guid`, `name`, `slug`, `category`, `first_seen_at`, `last_seen_at`.

### `soldier_vehicle_stats`

Composite PK: (`soldier_id`, `vehicle_id`).

Columns: `soldier_id`, `vehicle_id`, `kills`, `time_in_seconds`, `destroy_x_in_y`, `source_fetched_at`, `updated_at`.

## Collection state

### `collection_state`

**Critical row-shape rule:** `collection_state` is **one row per soldier**. `soldier_id` is its PK/FK CASCADE. It is NOT one row per (`soldier_id`, `resource`) and it has NO `resource` column.

Each resource is represented by a prefixed family of columns. For each of `detailed`, `profile`, `weapons`, and `vehicles`:

- `<resource>_state`
- `<resource>_last_attempt_at`
- `<resource>_last_success_at`
- `<resource>_next_due_at`
- `<resource>_consecutive_failures`
- `<resource>_last_error_class`
- `<resource>_last_error_message`

The table also has `updated_at`.

Every `<resource>_state` column is constrained to exactly one of:

- `never_attempted` — no collection attempt has yet been recorded for that resource;
- `success` — the latest collection state is successful;
- `temporary_failure` — the latest attempt failed in a retryable/temporary manner;
- `unavailable` — the resource is currently classified as unavailable.

Example for detailed collection: use `detailed_state`, `detailed_last_success_at`, etc. Do **not** write `WHERE resource = 'detailed'` against this table. A pristine detailed-state predicate uses `detailed_state = 'never_attempted'`, not `detailed_state = 'never'`.

## Discovery cursor

### `discovery_state`

Columns: `source_name` PK, `last_alias_id`, `last_poll_at`, `last_success_at`, `last_error`, `updated_at`.

`last_alias_id >= 0`.

## Collector registry

### `collectors`

| Column | Notes |
|---|---|
| `collector_uuid` | UUID PK, default `gen_random_uuid()` |
| `collector_name` | required, non-empty |
| `hostname` | required, non-empty |
| `lane` | `background` or `interactive` |
| `egress_key` | required, non-empty |
| `enabled` | boolean |
| `drained` | boolean |
| `software_version` | nullable |
| `started_at` | nullable timestamptz |
| `last_heartbeat_at` | nullable timestamptz |
| `heartbeat_state` | `unknown`, `healthy`, `lost` |
| `heartbeat_lost_at` | nullable timestamptz |
| `current_job_id` | nullable FK to `collection_jobs.job_id`, SET NULL |
| `created_at` | timestamptz |
| `updated_at` | timestamptz |
| `retired_at` | nullable timestamptz |

Active collector names are case-insensitively unique where `retired_at IS NULL`.

## Collection queue

### `collection_jobs`

**This table DOES have a `resource` column.** Resource filtering such as `resource = 'detailed'` belongs here.

Columns:

- `job_id` bigint identity PK
- `soldier_id` FK -> `soldiers` CASCADE
- `resource`
- `lane`
- `priority_class`
- `reason`
- `status`
- `priority_value`
- `eligible_at`
- `attempt_count`
- `collector_uuid` nullable FK -> `collectors`, SET NULL
- `lease_token` nullable UUID
- `claimed_at`
- `started_at`
- `lease_expires_at`
- `last_error_class`
- `last_error_at`
- `created_at`
- `updated_at`

Unique: (`soldier_id`, `resource`).

Lease-shape constraint:

- `pending`: no owner/token/claim/start/expiry
- `claimed`: owner/token/claimed/expiry required, `started_at` NULL
- `running`: owner/token/claimed/start/expiry required

This ownership shape plus the lease token is part of stale-owner fencing.

## Manual request ledger (feature branch migration 0009; not live)

### `manual_collection_requests`

`request_id` bigint identity PK; `soldier_id` bigint FK to `soldiers` RESTRICT;
`request_kind` text (`add`, `refresh`); `status` text (`accepted`, `queued`,
`collecting`, `completed`, `retrying`, `rejected`); `requested_at` timestamptz;
`completed_at` nullable timestamptz; `status_detail` nullable text.
Index on (`soldier_id`, `requested_at DESC`) and (`status`, `requested_at`).
This table is an audit ledger, **not** an executable queue. No application
permission is granted by this migration.

### `manual_request_cooldowns`

One row per soldier. `soldier_id` bigint PK/FK to `soldiers` CASCADE;
`last_accepted_at` timestamptz; `last_request_id` bigint FK to the request
ledger RESTRICT. The future request transaction must atomically serialize
per-soldier acceptance and enforce a 60-minute cooldown. A successful
collection does not itself reset this request cooldown.

## Collection event ledger

### `collection_events`

Append-style operational event ledger.

Columns: `event_id` PK, `occurred_at`, `collector_uuid`, `collector_name_snapshot`, `hostname_snapshot`, `egress_key_snapshot`, `job_id`, `soldier_id`, `persona_id`, `platform`, `resource`, `lane`, `event_type`, `attempt_number`, `result`, `duration_ms`, `http_status`, `error_class`, `error_message`, `lease_token`, `metadata` JSONB.

Several identity fields are intentionally nullable/snapshotted so historical events survive later registry/soldier changes.

Operational event semantics include:

- `collection_attempt_started`: committed immediately before a physical outbound collection request, so request evidence survives later normalization or persistence rollback;
- `collection_success` / `collection_failure`: normal terminal collection outcomes;
- `collection_persistence_failure`: a post-request database/persistence failure recorded in a fresh transaction after the failed persistence transaction rolls back. This is diagnostic evidence, not a second physical attempt.

Significant collection/persistence failures belong in this ledger as structured durable evidence as well as normal process/service logs. Routine debug/info log lines are not duplicated into PostgreSQL.

## Outbound request coordination

### `request_gates` (added in `0003_request_gates`)

One row per egress gate.

Columns:

- `egress_key` text PK, non-empty
- `next_request_at` timestamptz, required
- `updated_at` timestamptz, required, default `now()`

This is PostgreSQL-coordinated shared pacing state; it is not collector-local timing state.

## Stage 9C supervision run ledger (added in `0004_stage9c_supervision_runs`)

### `stage9c_supervision_runs`

This table is **not a collector heartbeat** and is not automatically
populated by the migration. It provides the future run-scoped coordination
surface for the Stage 9C watchdog and guards.

| Column | Notes |
|---|---|
| `run_id` | UUID primary key, explicitly generated by an authorized launcher |
| `state` | `prepared`, `active`, `aborted`, or `completed` |
| `cutover_at` | timezone-aware immutable accepted cutover (enforced by application logic) |
| `since_event_id` | bigint nonnegative exclusive event boundary |
| `started_at`, `deadline_at` | nullable until activation; deadline exactly six hours after start |
| `watchdog_owner` | nullable UUID writer identity |
| `watchdog_generation` | nonnegative bigint, default 0, for writer fencing |
| `heartbeat_at`, `lease_expires_at` | nullable timestamptz; active rows require an ordered lease |
| `abort_at`, `abort_reason` | nullable paired fields; aborted rows require both |
| `created_at`, `updated_at` | timestamptz, default now(); updates must explicitly advance updated_at |

A partial unique index permits at most **one** `state='active'` row.
Checks enforce legal states, nonnegative boundary/generation, activation
dates, six-hour deadline, active lease shape, and abort metadata pairing.
The migration does **not** install triggers for state transitions:
immutable boundary, monotonic generations, sticky abort, lease fencing,
and database-time freshness comparisons **must be implemented and tested
in transactional application SQL before activation**. Never interpret
the presence of this table as permission to start Stage 9C.

The migration does not modify `collection_jobs`, `collection_events`,
`collectors`, or `request_gates`. Existing Stage 9B evidence and
pending retry debt remain untouched. Operational scripts that hardcode
Alembic head `0003_request_gates` require a coordinated revision-policy
update before applying `0004` to the production database.

## Dispatch and soak ledgers (migrations 0005–0007)

### `outbound_dispatches` (0005, modified in 0007)

Columns: `dispatch_id` UUID primary key, `job_id` bigint, `attempt_number` integer, `resource` text, `lease_token` UUID, `collector_uuid` UUID, `egress_key` text, `lane` text, `payload_fingerprint` text, `admitted_at` timestamptz, `phase` text (default `admitted`), `send_marked_at` timestamptz nullable, `acknowledged_at` timestamptz nullable, and (0007) `request_ordinal` integer not null, default 1, check > 0.

`phase` must be `admitted`, `may_have_sent`, `acknowledged`, or `ambiguous`; check constraints enforce positive job/attempt, legal resource/lane, nonblank egress/fingerprint, phase-specific timestamps and chronological send/ack markers. No FK is declared for job or collector identities in this ledger.

At 0005–0006, unique identity is (`job_id`, `attempt_number`, `resource`, `lease_token`). Migration 0007 **replaces** it with (`job_id`, `attempt_number`, `resource`, `lease_token`, `request_ordinal`), allowing multiple physical HTTP requests per job attempt. Indexes: `ix_outbound_dispatch_background_admitted` (partial `lane='background'`), `ix_outbound_dispatch_egress_admitted` (`egress_key`, `admitted_at`), and at 0007 `ix_outbound_dispatch_admitted_at` (`admitted_at`). The 0005 and 0007 downgrades refuse when dispatch evidence exists.

### Stage 9C soak attribution (0006)

- `soak_runs`: `run_id` text PK, `cohort_digest` text, `baseline_event_id` bigint, `attempt_ceiling` and `site_attempt_ceiling` integer, nullable `start_at`/`deadline_at` timestamptz, `state` text default `prepared`, nullable `stop_reason`, `created_at`/`updated_at` timestamptz. State domain: `prepared`, `running`, `stopping`, `completed`, `failed`, `stopped`.
- `soak_rounds`: composite PK (`run_id`, `round_number`), `run_id` FK to `soak_runs` RESTRICT, `round_number` integer 1–12, `eligible_at` timestamptz, `state` text default `planned`, nullable `enqueued_at`/`completed_at`. State domain: `planned`, `enqueued`, `completed`, `failed`.
- `soak_round_jobs`: composite PK (`run_id`, `round_number`, `soldier_id`), composite FK to `soak_rounds` RESTRICT, `job_id` bigint unique, `outcome` text default `pending`. Outcome domain: `pending`, `success`, `failed`, `abandoned`. Index `ix_soak_round_jobs_round` on (`run_id`, `round_number`).

**Deployment note:** Migration 0006's docstring explicitly restricted application to isolated Stage 9C scratch testing. However, a read-only production check on 2026-10-14 UTC found `bf4_playerstats` already at `0006_stage9c_soak_round_ledger`, with zero `outbound_dispatches` and zero `soak_runs` rows at that instant. This documents an observed state, not retroactive approval for the original deployment. Migration 0007 is an explicit, separate production change; inspect live schema and ledger again before applying. This reference describes migration head, not a claim that production is already at head.

## Foreign-key relationship summary

- `soldier_sources.soldier_id` -> `soldiers` CASCADE
- `soldier_names.soldier_id` -> `soldiers` CASCADE
- `profile_soldiers.profile_id` -> `battlelog_profiles` CASCADE
- `profile_soldiers.soldier_id` -> `soldiers` CASCADE
- current/history/weapon/vehicle/collection-state soldier references -> `soldiers` CASCADE
- `collection_jobs.collector_uuid` -> `collectors` SET NULL
- `collectors.current_job_id` -> `collection_jobs` SET NULL
- `collection_events.collector_uuid` -> `collectors` SET NULL
- `collection_events.soldier_id` -> `soldiers` SET NULL

## Known SQL foot-guns

1. **Do not assume `collection_state.resource` exists.** It does not. Use resource-prefixed columns.
2. **Do not abbreviate collection-state domain values.** The pristine value is `never_attempted`; `never` is invalid. Check the exact domain above before writing predicates.
3. **Do not assume detailed current/history share timestamp names.** Current = `source_fetched_at`; history = `observed_at`.
4. **Do not resurrect `gun_master_score`.** It is intentionally absent at current head.
5. **Do not claim a job with an arbitrary collector UUID.** `collection_jobs.collector_uuid` is FK-constrained to `collectors`; register the collector first.
6. **Do not bypass the queue ownership tuple.** Job ownership is not merely `job_id`; collector UUID + lease token participate in fencing.
7. **Do not duplicate feeder eligibility from memory.** When a harness must predict feeder selection, compare its SQL directly with the production feeder implementation.
8. **Do not assume a migration file alone describes current head.** Apply every later migration mentally/documentarily; e.g. `0001` contains Gun Master columns that `0002` removes.

## Maintenance rule

Every schema-changing Alembic migration must update this document in the **same feature branch/change set**. A schema change is not considered implementation-complete until:

1. the migration exists;
2. upgrade/downgrade behavior is tested where applicable;
3. this reference reflects the resulting head schema; and
4. SQL/persistence code is checked against the resulting schema.

The next planned improvement is a schema-introspection validation utility that compares selected critical invariants in this reference against a live BF4PS database. The utility should validate rather than generate authoritative schema: Alembic remains the executable source of truth.
## Proposed 0013 indexed leaderboard read models — feature branch only

The production database remains at observed revision `0012_manual_verify_api`. Migration `0013_indexed_equipment_rankings` is **not deployed** and must be rehearsed on isolated PostgreSQL before promotion. The original section above is historical and not an assertion that production is at `0009`.

`weapon_leaderboard_metrics`: composite primary key (`soldier_id`, `weapon_id`), `kills bigint NOT NULL`, `kpm numeric NULL`, `accuracy numeric NULL`, `source_fetched_at timestamptz NOT NULL`. Both IDs reference their source tables with `ON DELETE CASCADE`. Ordered indexes `(weapon_id, kills DESC NULLS LAST, soldier_id)`, `(weapon_id, kpm DESC NULLS LAST, soldier_id)`, `(weapon_id, accuracy DESC NULLS LAST, soldier_id)`.

`vehicle_leaderboard_metrics`: composite primary key (`soldier_id`, `vehicle_id`), `kills bigint NOT NULL`, `kpm numeric NULL`, `source_fetched_at timestamptz NOT NULL`. `vehicle_id` is the **canonical family ID**, not necessarily a raw source vehicle ID. Ordered indexes `(vehicle_id, kills DESC NULLS LAST, soldier_id)` and `(vehicle_id, kpm DESC NULLS LAST, soldier_id)`.

The migration is intentionally inert: no automatic backfill, no triggers, no API cutover. Metric population, family mapping parity, live collector transaction integration, exclusions, tie ranks, population and percentile correctness are separate mandatory gates. Do not query these empty tables in production until backfill and ongoing maintenance are verified. The schema remains under review and may change before deployment.

## Migration 0018: distributed equipment ranking queue

Production revision confirmed on MAK-DB-02 (2026-10-22). Migration `0018_distributed_rank_queue` adds:

- `equipment_rank_capacity`: `id` smallint primary key constrained to `1`, `max_active_builds` integer (default 1), `lease_seconds` integer (default 180); bounds enforced by check constraints.
- `equipment_rank_workers`: `worker_id` UUID primary key, `hostname` text required, `site` text nullable, `started_at` and `heartbeat_at` timestamptz with `now()` defaults.
- `equipment_rank_jobs`: composite primary key (`kind`, `item_id`, `platform`, `metric`); `next_due_at`, `claimed_by` (FK to `equipment_rank_workers.worker_id`), `claim_token`, `claim_epoch`, `lease_expires_at`, `attempts`, `last_success_at`, `last_error`, `updated_at`. `kind` is `weapon` or `vehicle`; platform is `all`, `pc`, `ps4`, or `xboxone`.

The migration creates scheduling/coordination state; it does not change the existing `soldier_weapon_stats` and `soldier_vehicle_stats` row shapes.

## Candidate migration 0020: compact ranking snapshots (NOT DEPLOYED)

The feature branch `feature/compact-rank-snapshots` introduces additive migration
`0020_compact_rank_snapshots`, following production head `0019_soldier_search_trigrams`.
Production remains on 0019 until an explicitly approved rollout. Existing
`equipment_rank_rows` and `equipment_rank_published` remain untouched.

- `equipment_rank_compact_blocks`: PK `(generation_id, block_id)`; FK generation
  with cascading delete; first/last position and binary immutable payload.
- `equipment_rank_compact_lookup`: PK `(generation_id, soldier_id)`; block ID and
  zero-based block offset; FK `(generation_id, block_id)` to compact blocks with
  cascading delete; secondary `(soldier_id, generation_id)` index.
- `equipment_rank_compact_published`: scope PK `(kind, item_id, platform, metric)`;
  generation FK; timestamp. This pointer is independent of legacy publication.

Migration 0020 is **schema only** until the writer, reader, parity, exclusion
validation, and safe generation retention have been implemented and tested.
Do not activate compact publication or drop legacy storage from this migration.

The candidate codec `player-collector/bf4ps/compact_rank_codec.py` uses
`BF4RC1`-prefixed zlib-compressed JSON arrays of up to 1000 immutable rows.
Each row stores soldier ID, competition rank, kills, KPM, accuracy, and fetched
at. KPM/accuracy are serialized as decimal strings to avoid precision loss.
The payload does not include soldier names; these must be read from `soldiers`
using the same read snapshot and the compact lookup index.

## Compact ranking integration (feature branch, NOT ACTIVE)

`player-collector/build_compact_rank.py` builds immutable blocks and per-soldier
lookup records. Its default mode rolls back. Publication is restricted to the
`bf4ps_ranking_scratch` database; production publishing is explicitly rejected
until distributed lease fencing, retention and parity tests are complete.

`website/api/rank_read_path_compact.py` is a separately gated candidate reader.
`BF4PS_COMPACT_RANK_READS=1` enables it only when the new schema exists and a
valid compact pointer is present; do not set this in production yet. The reader
falls back when no valid generation exists or when an excluded identity remains
in the generation. It preserves rank ties, immutable scores, names and persona
search, pagination and division calculations. Current candidate scans all
compressed blocks for division and filtered counts; performance and search
parity require measurement before deployment.

No production schema migration, ranking writer, feature flag, or table cleanup
has been executed as part of this branch. Legacy rankings remain unchanged.

### Candidate test coverage (2026-10-31)

`website/tests/test_compact_rank_reader.py` exercises the gated reader with a
fake SQL connection: tied ranks, pagination, exact numeric score precision,
name/persona filtering, divisions, and fallback on exclusion or missing
publication. These are **unit tests, not a migrated PostgreSQL integration
harness**. Do not claim the 0020 end-to-end scratch test has passed until the
migration is applied to a disposable PostgreSQL database and the real builder,
reader, and cleanup paths are exercised together. The builder currently
materializes the ranked query result before inserts to avoid interleaving a
server-side cursor and DML on the same connection. Production writer fencing,
search performance, generation retention, and complete migration validation
remain release blockers.

## Migration 0021: reconcile externally provisioned player exclusions

Production inspection on MAK-DB-02 confirmed `public.player_exclusions` exists
outside Alembic head 0019. Its composite PK is `(platform, persona_id)`;
fields: `reason_code text NOT NULL`, `private_note text NULL`,
`created_by text NOT NULL`, `created_at timestamptz NOT NULL DEFAULT now()`,
`updated_at timestamptz NOT NULL DEFAULT now()`, and
`active boolean NOT NULL DEFAULT true`. Constraints enforce persona ID > 0
and platform in `pc`, `ps4`, `xboxone`. A partial btree index
`ix_player_exclusions_active` covers `(platform, persona_id) WHERE active`.
The `bf4ps_exclusion_soldiers` trigger runs before soldier insert or
persona/platform update, calling security-definer
`public.bf4ps_reject_excluded_soldier()` (fixed pg_catalog/pg_temp search path)
to reject active exclusions with SQLSTATE 23514.

Additive migration `0021_reconcile_player_exclusions` creates these objects on
fresh installations and validates the table shape on existing installations.
It does not drop them on downgrade, to preserve pre-existing production
moderation safeguards. No migration has been applied to production.

### Compact candidate stress/retention notes (RNT-01 isolated PostgreSQL)

100,003 synthetic PC weapon soldiers: 6.18 s build/publish, 74 MB peak
Python RSS, 685 KB compressed payload, about 12.5 MB block + lookup
relation storage. Page/search/division reads were 0.28–0.48 s locally.
Synthetic data compressibility and latency are not representative of actual
player distributions. Reader now requires generation input scope version to
match the current scope version, failing closed after source invalidation.
Scratch publication can validate an optional worker/token/epoch lease under
row lock; production publication remains prohibited. Scratch-only
`cleanup_compact_rank.py` preserves published and newest two generations per
scope, and excludes any legacy rank references. No production cleanup enabled.

### RNT-01 end-to-end scratch results (2026-10-31)

On a separate localhost-only PostgreSQL 16.15 cluster (port 55432), applied
migrations 0001 through 0021, seeded 100,003 synthetic soldiers and published
multiple compact generations. Real reader returned correct name/persona
searches, tied ranks, pagination and divisions. Direct PostgreSQL window-rank
comparison matched soldier IDs, competition ranks and deterministic positions
on pages 1, 10, 500, 1000 and 2001. After incrementing the source scope
version inside a transaction, the reader correctly fell back. Publishing with
an absent worker claim was rejected; a valid worker/token/epoch lease published.
Scratch retention deleted four unreferenced generations, preserved the newest
two (including the current publication pointer), and the reader remained
functional afterward. Targeted Python tests: 11 passed.

**Remaining production blockers:** realistic data and concurrent worker stress;
complete website route/response parity and error handling; production migration
review and access grants; an enforced (not optional) distributed claim for any
future production writer; robust orphan generation cleanup; and testing
production-size WAL, replica replay and rollback. Feature flag remains off.

### Additional safety review (candidate)

Compact publication now requires worker UUID, claim UUID, and claim epoch
regardless of database; production publication is still explicitly blocked.
The website HTTP leaderboard handler now selects REPEATABLE READ and bypasses
its process-local Top-10 cache when compact reads are enabled, matching the
precomputed reader's transaction isolation and cache behavior. The compact
reader is still disabled by default. Full live HTTP response compatibility,
replica/WAL impact, and production access grants require verification.

### Production privilege reconnaissance (read-only, 2026-10-31)

Current primary `mak-db-02` has application roles including
`bf4ps_stage9c_d2`, `bf4ps_stage9c_d4`, `bf4ps_admin_moderation`, and
`bf4_playerstats_test_migrator`. `bf4ps_stage9c_d2` has SELECT on
`equipment_rank_generations`, `equipment_rank_scope_versions`, and
`player_exclusions`; it has no observed DML grants on ranking generation
or job tables in the inspected grants. New compact tables do not yet exist
in production, so no reader/writer grants have been provisioned. Dedicated
least-privilege compact reader and writer roles/grants must be designed and
verified before production activation. No grants changed in this audit.

### Isolated HTTP and concurrency validation (RNT-01)

With `BF4PS_ISOLATED_HTTP_TEST=1` and compact reads enabled, the real
`leaderboard_api.py` was launched on localhost port 18765 against the scratch
PostgreSQL cluster. HTTP 200 responses verified page 1 and deep page 2001,
name search, divisions 1 and 10, and accuracy sort; invalid page/sort returned
HTTP 400. The isolated HTTP database exception is allowed only when the
requested database is exactly `bf4ps_ranking_scratch` and PostgreSQL server
address is loopback; the production database guard is otherwise unchanged.

Two simultaneous 100,003-player builders using a valid versus deliberately
invalid claim token produced one successful publication (generation 10) and
one rejected stale-claim publication. An earlier attempt with an expired
lease correctly rejected both builders. One isolated 100,003-row generation
and pointer publication produced approximately **47 MB of WAL** as measured
by `pg_current_wal_lsn()` difference; this is a synthetic-data, local-only
measurement, not an HA replica replay measurement. Production primary
read-only check showed three async streaming replicas and 0-byte replay lag
at observation. No production rank writes or migrations occurred.

TCOU production leaderboard loopback HTTP smoke check returned 200 with the
existing response envelope (population/filtered_count/page/page_size/
total_pages/rows). No website service restart or production flag change.

**Unfinished:** complete HTTP parity across vehicle-family aggregation and
all platform/metric combinations, production grants, real-data WAL/replica
soak, and production publication rollout. Keep production feature disabled.

### Cross-platform compact verification

RNT-01 scratch HTTP comparison passed 20 of 20 combinations (weapon kills/KPM/accuracy and vehicle kills/KPM, each on PC/PS4/Xbox/ALL). PC population 100003, PS4 2, Xbox 2, ALL 100007. Compared JSON top-10 IDs, ranks, positions, population against direct PostgreSQL window functions. Multi-variant vehicle families use legacy SUM/MAX aggregation from raw stats; compact single-item metric source is not yet proven equivalent. The website now explicitly falls back for these families. Production remains disabled.

### Isolated physical streaming replica check

RNT-01 scratch primary port 55432 was cloned via pg_basebackup to a second PostgreSQL 16 cluster on localhost port 55433 (hot standby). Under repeated 100003-player compact publications, pg_stat_replication showed streaming async replay with 2024 bytes of replay lag at one observation. Direct compact reader against standby returned population 100003 and 50 rows. This tests physical WAL replay locally, not real-data WAN replication or production latency. No production replica changed. Verified audited multi-variant vehicle family request (canonical item 2) bypasses compact reader and uses legacy fallback. Production roles and grants remain a rollout gate.

### Repeated publication standby replay stress

RNT-01 localhost PostgreSQL primary and physical standby replayed a second full 20-scope publication matrix (100003 PC, 100007 ALL for large scopes). Total elapsed 78.48 seconds; WAL LSN advanced approximately 290 MB across the matrix, including PostgreSQL overhead. Standby remained streaming with 2024 bytes replay gap during workload and 0 bytes after completion. Read-only compact reader on standby returned 50 rows and population 100003. Same-host scratch synthetic-data benchmark only: WAN production replica performance and real-data compression remain unverified. Added automated vehicle-family fallback guard test; 12 targeted tests passed.
