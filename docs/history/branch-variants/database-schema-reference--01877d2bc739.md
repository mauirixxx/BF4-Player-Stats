# BF4 Player Stats database schema reference

Status: **developer reference for the current Alembic head**

Current documented head: `0005_stage9c_dispatch_ledger` (inert D2 schema only; production HOLD)

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
| `0005_stage9c_dispatch_ledger` | `0004_stage9c_supervision_runs` | Adds inert durable outbound dispatch evidence table; no HTTP admission or activation |

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

## Stage 9C inert outbound dispatch ledger (0005)

`outbound_dispatches` is **DDL only**, not integrated into production collectors or admission logic. Production remains HOLD; the 1,296 actual-HTTP/hour guarantee is unresolved.

- `dispatch_id`: UUID primary key.
- Immutable identity columns: `job_id` bigint, `attempt_number` integer, `resource` text, `lease_token` UUID. Unique `(job_id, attempt_number, resource, lease_token)`.
- Ownership and request binding: `collector_uuid` UUID, `egress_key` text, `lane` text, `payload_fingerprint` text; all required.
- Timestamps: `admitted_at` timestamptz required; `send_marked_at` and `acknowledged_at` nullable timestamptz.
- `phase`: `admitted`, `may_have_sent`, `acknowledged`, `ambiguous`; defaults to `admitted` with phase/timestamp consistency checks.
- Check constraints require positive job/attempt, valid resource/lane, nonempty egress and fingerprint, monotonic send/ack timestamps.
- Indexes: `ix_outbound_dispatch_background_admitted` (partial background lane) and `ix_outbound_dispatch_egress_admitted`.
- Deliberately **no foreign key** to mutable `collection_jobs`; evidence must not disappear on job deletion. Downgrade refuses when the ledger is nonempty.
- There is no automated admission implementation, no transport hook, and no authorization to send HTTP from this table.
