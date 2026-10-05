# BF4 Player Stats database schema reference

Status: **developer reference for the current Alembic head**

Current documented head: `0003_request_gates`

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

## Collection event ledger

### `collection_events`

Append-style operational event ledger.

Columns: `event_id` PK, `occurred_at`, `collector_uuid`, `collector_name_snapshot`, `hostname_snapshot`, `egress_key_snapshot`, `job_id`, `soldier_id`, `persona_id`, `platform`, `resource`, `lane`, `event_type`, `attempt_number`, `result`, `duration_ms`, `http_status`, `error_class`, `error_message`, `lease_token`, `metadata` JSONB.

Several identity fields are intentionally nullable/snapshotted so historical events survive later registry/soldier changes.

## Outbound request coordination

### `request_gates` (added in `0003_request_gates`)

One row per egress gate.

Columns:

- `egress_key` text PK, non-empty
- `next_request_at` timestamptz, required
- `updated_at` timestamptz, required, default `now()`

This is PostgreSQL-coordinated shared pacing state; it is not collector-local timing state.

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
