# BF4PS PostgreSQL Schema Design v1

This document defines the initial PostgreSQL data model for BF4 Player Stats (BF4PS). It is the architectural contract for migration 0001. Changes to these decisions must be documented with the migration that changes them.

## Goals

- Keep BF4SW operational data separate from BF4PS-owned data.
- Use BF4SW read-only as a seed/discovery source for known soldiers.
- Make BF4 soldier identity independent of mutable player names and Battlelog profile privacy.
- Retain compact historical overall-stat snapshots.
- Keep weapon and vehicle data as replaceable current state in v1.
- Normalize static weapon/vehicle metadata into catalogs.
- Never store entire Battlelog JSON payloads as the primary data model.
- Make polling/retry state explicit rather than inferring it from gameplay data.

## Identity rules

The stable gameplay identity is the pair `(persona_id, platform)`.

BF4PS uses an internal surrogate `soldier_id bigint generated ... identity` as the relational primary key, while enforcing a unique constraint on `(persona_id, platform)`. The surrogate keeps foreign keys compact and prevents platform strings from being repeated through every statistics table.

Supported initial platform values are `pc`, `ps4`, and `xboxone`. The collector maps these to Battlelog platform integers 1, 32, and 64 respectively.

Names are mutable attributes, never primary keys.

## Tables

### soldiers

One row per BF4 persona/platform identity.

Core columns:

- `soldier_id bigint` PK;
- `persona_id bigint NOT NULL`;
- `platform text NOT NULL`;
- `current_name text NOT NULL`;
- `first_seen_at timestamptz NOT NULL`;
- `last_seen_at timestamptz NOT NULL`;
- `created_at timestamptz NOT NULL`;
- `updated_at timestamptz NOT NULL`.

Constraints/indexes:

- UNIQUE `(persona_id, platform)`;
- CHECK platform in the supported set;
- index on case-insensitive current-name lookup (for example `lower(current_name)`);
- index on `last_seen_at` for collector prioritization.

### soldier_sources

Records every independent way a soldier became known to BF4PS. Discovery provenance is many-to-one: the same soldier may be discovered manually and later observed by BF4SW without changing identity or losing either fact.

Core columns:

- `soldier_id bigint` FK -> soldiers ON DELETE CASCADE;
- `source_type text NOT NULL`;
- `first_seen_at timestamptz NOT NULL`;
- `last_seen_at timestamptz NOT NULL`.

Primary key: `(soldier_id, source_type)`. Initial source types are `bf4sw` and `manual`. Future discovery mechanisms may add source types without altering the soldier identity model.

A manual submission of an already-known BF4SW soldier adds/refreshes the `manual` provenance row rather than creating a duplicate soldier. Likewise, a manually seeded inactive soldier can later acquire a `bf4sw` source if that player returns to the game.

### soldier_names

Historical alias/name observations for a soldier.

Core columns:

- `soldier_name_id bigint` PK;
- `soldier_id bigint` FK -> soldiers ON DELETE CASCADE;
- `name text NOT NULL`;
- `first_seen_at timestamptz NOT NULL`;
- `last_seen_at timestamptz NOT NULL`.

Constraint: UNIQUE `(soldier_id, name)`.

A collector seeing a known alias again updates `last_seen_at`; a newly observed spelling/name creates a row and updates `soldiers.current_name` when that source is considered authoritative/current.

### battlelog_profiles

Optional account-level profile enrichment. A profile is not required for a soldier to exist or be collected.

Core columns:

- `profile_id bigint` PK;
- `battlelog_username text NOT NULL`;
- `battlelog_user_id bigint NULL`;
- `country_code char(2) NULL`;
- `country_name text NULL`;
- `access_state text NOT NULL`;
- `last_checked_at timestamptz NULL`;
- `last_success_at timestamptz NULL`;
- `last_error text NULL`;
- `created_at timestamptz NOT NULL`;
- `updated_at timestamptz NOT NULL`.

Initial access states: `public_country`, `public_no_country`, `friends_only`, `not_found`, and `error`.

Country code is normalized uppercase. `error` is an operational result, not evidence that country is absent.

Use a case-insensitive unique index on Battlelog username. The nullable numeric Battlelog user ID is not required for v1 operation but is available if reconnaissance/implementation can populate it reliably.

### profile_soldiers

Maps Battlelog profiles/accounts to BF4 soldiers.

Columns:

- `profile_id bigint` FK -> battlelog_profiles ON DELETE CASCADE;
- `soldier_id bigint` FK -> soldiers ON DELETE CASCADE;
- `first_seen_at timestamptz NOT NULL`;
- `last_seen_at timestamptz NOT NULL`.

Primary key: `(profile_id, soldier_id)`.

Do not impose a unique constraint on `soldier_id` in v1. We have confirmed one account can expose multiple soldiers; we have not established enough rename/account-transfer behavior to make the inverse relationship an irreversible database constraint.

### detailed_stats_current

One current normalized detailed-stat row per soldier.

Primary key/FK: `soldier_id bigint` -> soldiers ON DELETE CASCADE.

It contains the RAW fields from Detailed Stats Retention Contract v1, including rank, time played, score categories, game-mode scores, kills/deaths/assists/wins/losses/shots, team/objective counters, extra counters, and Battlelog's authoritative `quitPercentage`.

Additional metadata:

- `source_fetched_at timestamptz NOT NULL`;
- `updated_at timestamptz NOT NULL`.

Derived values such as K/D, KPM, SPM, combat SPM, and accuracy are not columns.

### detailed_stats_history

Append-only historical snapshots of the same retained RAW detailed-stat contract.

Columns:

- `snapshot_id bigint` PK;
- `soldier_id bigint` FK -> soldiers ON DELETE CASCADE;
- all RAW retained detailed-stat fields;
- `observed_at timestamptz NOT NULL`.

Indexes:

- `(soldier_id, observed_at DESC)`;
- optional BRIN on `observed_at` once table volume justifies it.

Snapshot rule: append when the supported overall state differs from the most recent stored snapshot. Do not create duplicate snapshots solely because another poll occurred. `detailed_stats_current` is updated on every successful normalized fetch; history records meaningful state observations.

The current and history tables intentionally duplicate the retained columns. Current-state queries stay cheap while history remains append-only and simple to reason about. A JSONB snapshot is deliberately rejected for v1 because these fields are known, queryable, and form an explicit contract.

### weapon_catalog

Static/reference identity for Battlelog weapons.

Core columns:

- `weapon_id bigint` PK;
- `weapon_guid text NOT NULL UNIQUE`;
- `name text NOT NULL`;
- `slug text NULL`;
- `category text NULL`;
- `first_seen_at timestamptz NOT NULL`;
- `last_seen_at timestamptz NOT NULL`.

Catalog metadata can be refreshed when Battlelog provides better values. UI image/unlock/progression blobs are not stored.

### soldier_weapon_stats

Current weapon state only.

Columns:

- `soldier_id bigint` FK;
- `weapon_id bigint` FK;
- `kills bigint NOT NULL`;
- `headshots bigint NOT NULL`;
- `shots_fired bigint NOT NULL`;
- `shots_hit bigint NOT NULL`;
- `time_equipped_seconds bigint NOT NULL`;
- `source_fetched_at timestamptz NOT NULL`;
- `updated_at timestamptz NOT NULL`.

Primary key: `(soldier_id, weapon_id)`.

KPM, accuracy, HSKR, and kills-per-hit are derived. No weapon history table exists in schema v1.

A successful complete weapon refresh is treated as authoritative current state: upsert rows present in the response and remove/zero stale player-weapon rows according to collector semantics established during implementation. A partial/failed response must never erase current state.

### vehicle_catalog

Static/reference identity for Battlelog vehicles.

Core columns mirror weapon_catalog:

- `vehicle_id bigint` PK;
- `vehicle_guid text NOT NULL UNIQUE`;
- `name text NOT NULL`;
- `slug text NULL`;
- `category text NULL`;
- first/last-seen timestamps.

### soldier_vehicle_stats

Current vehicle state only.

Columns:

- `soldier_id bigint` FK;
- `vehicle_id bigint` FK;
- `kills bigint NOT NULL`;
- `time_in_seconds bigint NOT NULL`;
- `destroy_x_in_y bigint NULL` only if implementation confirms the field is required/meaningful for supported display;
- `source_fetched_at timestamptz NOT NULL`;
- `updated_at timestamptz NOT NULL`.

Primary key: `(soldier_id, vehicle_id)`.

Vehicle KPM and formatted time are derived. No vehicle history table exists in schema v1.

### collection_state

Operational state belongs outside gameplay-stat rows.

One row per soldier:

- `soldier_id bigint` PK/FK;
- `detailed_last_attempt_at`, `detailed_last_success_at`, `detailed_next_due_at`;
- `weapons_last_attempt_at`, `weapons_last_success_at`, `weapons_next_due_at`;
- `vehicles_last_attempt_at`, `vehicles_last_success_at`, `vehicles_next_due_at`;
- `profile_last_attempt_at`, `profile_last_success_at`, `profile_next_due_at`;
- per-source consecutive failure counters;
- per-source last error class/message as needed;
- `updated_at timestamptz NOT NULL`.

This separates scheduling/failure bookkeeping from the authoritative last-good statistics. A failed Battlelog request must not overwrite or invalidate the last known good stats.

Indexes on the `*_next_due_at` columns support efficient collector work selection.

## Discovery and seeding

BF4PS has two first-class discovery paths in v1: continuous BF4SW discovery and explicit manual submission. Neither source owns the soldier record.

### Continuous BF4SW discovery

BF4SW is an ongoing source, not a one-time import. A BF4PS discovery job periodically queries the BF4SW database using a dedicated read-only account for newly observed or changed soldier identities. The job upserts BF4PS `soldiers`, `soldier_names`, and `soldier_sources` records and schedules newly discovered soldiers for Battlelog collection.

The discovery process must be incremental and idempotent. Re-reading an already-known `(persona_id, platform)` must not create duplicates. The implementation should use a durable BF4PS-side discovery cursor/watermark where the BF4SW source data provides a suitable monotonic timestamp or identifier; otherwise it may safely rescan the relevant identity set and rely on upserts. The exact cadence belongs to collector configuration rather than schema v1.

A temporary BF4SW/database outage delays discovery only. It must not prevent BF4PS from serving existing data or collecting Battlelog statistics for already-known soldiers.

### Manual submission

Manual submission exists specifically so BF4PS can collect valid Battlelog soldiers that BF4SW has never observed, including players inactive for years.

Preferred input is a normal BF4 Battlelog soldier URL because it encodes the soldier name, persona ID, and platform. Administrative/API input may also accept an explicit name, persona ID, and platform tuple.

Before a previously unknown manual identity is accepted, BF4PS validates the persona/platform against Battlelog's lightweight detailed-statistics endpoint. A successful valid response creates/upserts the soldier, records `source_type = manual`, and schedules detailed, weapon, vehicle, and optional profile enrichment. Invalid/unresolvable submissions do not create a normal collectable soldier record.

Submitting an identity already present from BF4SW does not duplicate it; it adds/refreshes manual provenance and may request a prompt refresh. Names remain mutable observations and are never identity keys.

Once accepted, manually seeded soldiers participate in normal collector scheduling. Collection cadence may later back off substantially for inactive/manual-only soldiers whose cumulative stats remain unchanged, while recent BF4SW activity can justify faster refreshes. That is scheduling policy, not identity semantics.

## BF4SW integration boundary

BF4PS must not add foreign keys into the BF4 Server Watcher database and must not write to BF4SW tables.

The BF4PS importer/discovery process connects to BF4SW with a read-only account and copies/updates identity observations into BF4PS-owned `soldiers`, `soldier_names`, and `soldier_sources` rows. This is an application-level integration boundary, not a cross-database relational dependency.

BF4PS remains usable if BF4SW is temporarily unavailable; existing BF4PS identities and statistics remain queryable and collectable.

## Data types and normalization

- Persona IDs use PostgreSQL `bigint`.
- Cumulative counters use `bigint` unless reconnaissance proves a signed/non-integral source semantic.
- Time counters are stored as integer seconds.
- Battlelog's `quitPercentage` uses a numeric/double-compatible type; implementation should preserve enough precision to reproduce the source display.
- Country codes are uppercase two-character values.
- All timestamps use `timestamptz` and are stored in UTC by PostgreSQL convention.
- Source nulls are normalized deliberately; collector code must not blindly cast Battlelog JSON types.

## Derived-stat rules

Do not persist deterministic presentation values when the retained raw counters reproduce them:

- K/D = kills / deaths;
- KPM = kills / (seconds / 60);
- SPM = score / (timePlayed / 60);
- combat SPM = combatScore / (timePlayed / 60);
- accuracy = shots_hit / shots_fired;
- weapon HSKR = headshots / kills;
- weapon kills-per-hit = kills / shots_hit.

Division-by-zero behavior belongs in the query/application layer and must be consistent.

## History and retention

Overall detailed-stat history is retained indefinitely in v1. The expected rows are compact enough that premature pruning/partitioning is unnecessary.

Weapon and vehicle history is intentionally absent. Their current tables can later gain corresponding history tables without changing soldier/catalog identity.

No raw 0.5 MB weapon or vehicle response blobs are retained as routine historical data.

## Migration policy

Alembic is the migration mechanism. Migration 0001 must implement this documented schema rather than inventing additional persistence ad hoc.

Every later schema migration must include a documentation update when it changes table purpose, identity semantics, retention behavior, or source mapping. Migrations should be forward-safe and should not silently discard historical data.

## Deliberately deferred decisions

The following are not required to create schema v1:

- exact polling cadence and rate limiting;
- whether old history eventually needs partitioning/retention limits;
- weapon/vehicle history;
- presentation prose;
- whether `destroyXinY` earns a permanent supported field;
- production web/API caching strategy;
- authentication/user-account features for the future BF4PS website.

These decisions should be made from operational evidence rather than embedded prematurely in migration 0001.
