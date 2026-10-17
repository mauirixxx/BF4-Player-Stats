# BF4PS PostgreSQL live schema inventory

**Observed:** 2026-10-17 23:34 UTC  
**Database:** `bf4_playerstats`  
**PostgreSQL:** 16.15 (Ubuntu 16.15-0ubuntu0.24.04.1)  
**Alembic version:** `0012_manual_verify_api`  
**Tables:** 24  

## Scope and authority

This is a **read-only live catalog snapshot** from PostgreSQL on the BF4PS website database connection. It documents actual public tables, columns, constraints and indexes, not a speculative migration plan. Source-of-truth for intended schema evolution remains the collector Alembic migrations; reconcile differences before writing schema-dependent code.

The original inventory captured the weapon ranking index while its concurrent build was still in progress (`indisvalid=False`). **Post-build verification on 2026-10-17 confirmed `indisvalid=True`, `indisready=True`, and `indislive=True`**. The index occupies approximately 479 MB. The table below reflects the verified final state.

## Indexes

### `alembic_version`

| Index | Valid | Ready | Definition |
|---|---|---|---|
| `alembic_version_pkc` | True | True | `CREATE UNIQUE INDEX alembic_version_pkc ON public.alembic_version USING btree (version_num)` |

### `battlelog_profiles`

| Index | Valid | Ready | Definition |
|---|---|---|---|
| `battlelog_profiles_pkey` | True | True | `CREATE UNIQUE INDEX battlelog_profiles_pkey ON public.battlelog_profiles USING btree (profile_id)` |
| `uq_battlelog_profiles_username_lower` | True | True | `CREATE UNIQUE INDEX uq_battlelog_profiles_username_lower ON public.battlelog_profiles USING btree (lower(battlelog_username))` |

### `collection_events`

| Index | Valid | Ready | Definition |
|---|---|---|---|
| `collection_events_pkey` | True | True | `CREATE UNIQUE INDEX collection_events_pkey ON public.collection_events USING btree (event_id)` |
| `ix_collection_events_collector_time` | True | True | `CREATE INDEX ix_collection_events_collector_time ON public.collection_events USING btree (collector_uuid, occurred_at DESC)` |
| `ix_collection_events_http_errors` | True | True | `CREATE INDEX ix_collection_events_http_errors ON public.collection_events USING btree (http_status, occurred_at DESC) WHERE (http_status IS NOT NULL)` |
| `ix_collection_events_job` | True | True | `CREATE INDEX ix_collection_events_job ON public.collection_events USING btree (job_id, occurred_at) WHERE (job_id IS NOT NULL)` |
| `ix_collection_events_persona_time` | True | True | `CREATE INDEX ix_collection_events_persona_time ON public.collection_events USING btree (platform, persona_id, occurred_at DESC) WHERE (persona_id IS NOT NULL)` |
| `ix_collection_events_soldier_time` | True | True | `CREATE INDEX ix_collection_events_soldier_time ON public.collection_events USING btree (soldier_id, occurred_at DESC) WHERE (soldier_id IS NOT NULL)` |
| `ix_collection_events_time` | True | True | `CREATE INDEX ix_collection_events_time ON public.collection_events USING btree (occurred_at DESC)` |
| `ix_collection_events_type_time` | True | True | `CREATE INDEX ix_collection_events_type_time ON public.collection_events USING btree (event_type, occurred_at DESC)` |

### `collection_jobs`

| Index | Valid | Ready | Definition |
|---|---|---|---|
| `collection_jobs_pkey` | True | True | `CREATE UNIQUE INDEX collection_jobs_pkey ON public.collection_jobs USING btree (job_id)` |
| `ix_collection_jobs_claim` | True | True | `CREATE INDEX ix_collection_jobs_claim ON public.collection_jobs USING btree (lane, priority_class, priority_value DESC, eligible_at, created_at, job_id) WHERE (status = 'pending'::text)` |
| `ix_collection_jobs_collector` | True | True | `CREATE INDEX ix_collection_jobs_collector ON public.collection_jobs USING btree (collector_uuid) WHERE (collector_uuid IS NOT NULL)` |
| `ix_collection_jobs_expired_lease` | True | True | `CREATE INDEX ix_collection_jobs_expired_lease ON public.collection_jobs USING btree (lease_expires_at, job_id) WHERE (status = ANY (ARRAY['claimed'::text, 'running'::text]))` |
| `uq_collection_jobs_soldier_resource` | True | True | `CREATE UNIQUE INDEX uq_collection_jobs_soldier_resource ON public.collection_jobs USING btree (soldier_id, resource)` |

### `collection_state`

| Index | Valid | Ready | Definition |
|---|---|---|---|
| `collection_state_pkey` | True | True | `CREATE UNIQUE INDEX collection_state_pkey ON public.collection_state USING btree (soldier_id)` |
| `ix_collection_state_detailed_due` | True | True | `CREATE INDEX ix_collection_state_detailed_due ON public.collection_state USING btree (detailed_next_due_at) WHERE (detailed_next_due_at IS NOT NULL)` |
| `ix_collection_state_profile_due` | True | True | `CREATE INDEX ix_collection_state_profile_due ON public.collection_state USING btree (profile_next_due_at) WHERE (profile_next_due_at IS NOT NULL)` |
| `ix_collection_state_vehicles_due` | True | True | `CREATE INDEX ix_collection_state_vehicles_due ON public.collection_state USING btree (vehicles_next_due_at) WHERE (vehicles_next_due_at IS NOT NULL)` |
| `ix_collection_state_weapons_due` | True | True | `CREATE INDEX ix_collection_state_weapons_due ON public.collection_state USING btree (weapons_next_due_at) WHERE (weapons_next_due_at IS NOT NULL)` |

### `collectors`

| Index | Valid | Ready | Definition |
|---|---|---|---|
| `collectors_pkey` | True | True | `CREATE UNIQUE INDEX collectors_pkey ON public.collectors USING btree (collector_uuid)` |
| `ix_collectors_egress` | True | True | `CREATE INDEX ix_collectors_egress ON public.collectors USING btree (egress_key) WHERE (retired_at IS NULL)` |
| `ix_collectors_heartbeat` | True | True | `CREATE INDEX ix_collectors_heartbeat ON public.collectors USING btree (heartbeat_state, last_heartbeat_at) WHERE (retired_at IS NULL)` |
| `uq_collectors_active_name` | True | True | `CREATE UNIQUE INDEX uq_collectors_active_name ON public.collectors USING btree (lower(collector_name)) WHERE (retired_at IS NULL)` |

### `detailed_stats_current`

| Index | Valid | Ready | Definition |
|---|---|---|---|
| `detailed_stats_current_pkey` | True | True | `CREATE UNIQUE INDEX detailed_stats_current_pkey ON public.detailed_stats_current USING btree (soldier_id)` |

### `detailed_stats_history`

| Index | Valid | Ready | Definition |
|---|---|---|---|
| `detailed_stats_history_pkey` | True | True | `CREATE UNIQUE INDEX detailed_stats_history_pkey ON public.detailed_stats_history USING btree (snapshot_id)` |
| `ix_detailed_history_soldier_observed` | True | True | `CREATE INDEX ix_detailed_history_soldier_observed ON public.detailed_stats_history USING btree (soldier_id, observed_at DESC)` |

### `discovery_state`

| Index | Valid | Ready | Definition |
|---|---|---|---|
| `discovery_state_pkey` | True | True | `CREATE UNIQUE INDEX discovery_state_pkey ON public.discovery_state USING btree (source_name)` |

### `outbound_dispatches`

| Index | Valid | Ready | Definition |
|---|---|---|---|
| `ix_outbound_dispatch_admitted_at` | True | True | `CREATE INDEX ix_outbound_dispatch_admitted_at ON public.outbound_dispatches USING btree (admitted_at)` |
| `ix_outbound_dispatch_background_admitted` | True | True | `CREATE INDEX ix_outbound_dispatch_background_admitted ON public.outbound_dispatches USING btree (admitted_at) WHERE (lane = 'background'::text)` |
| `ix_outbound_dispatch_egress_admitted` | True | True | `CREATE INDEX ix_outbound_dispatch_egress_admitted ON public.outbound_dispatches USING btree (egress_key, admitted_at)` |
| `outbound_dispatches_pkey` | True | True | `CREATE UNIQUE INDEX outbound_dispatches_pkey ON public.outbound_dispatches USING btree (dispatch_id)` |
| `uq_outbound_dispatch_physical_identity` | True | True | `CREATE UNIQUE INDEX uq_outbound_dispatch_physical_identity ON public.outbound_dispatches USING btree (job_id, attempt_number, resource, lease_token, request_ordinal)` |

### `player_exclusions`

| Index | Valid | Ready | Definition |
|---|---|---|---|
| `ix_player_exclusions_active` | True | True | `CREATE INDEX ix_player_exclusions_active ON public.player_exclusions USING btree (platform, persona_id) WHERE active` |
| `player_exclusions_pkey` | True | True | `CREATE UNIQUE INDEX player_exclusions_pkey ON public.player_exclusions USING btree (platform, persona_id)` |

### `profile_soldiers`

| Index | Valid | Ready | Definition |
|---|---|---|---|
| `profile_soldiers_pkey` | True | True | `CREATE UNIQUE INDEX profile_soldiers_pkey ON public.profile_soldiers USING btree (profile_id, soldier_id)` |

### `request_gates`

| Index | Valid | Ready | Definition |
|---|---|---|---|
| `request_gates_pkey` | True | True | `CREATE UNIQUE INDEX request_gates_pkey ON public.request_gates USING btree (egress_key)` |

### `soak_round_jobs`

| Index | Valid | Ready | Definition |
|---|---|---|---|
| `ix_soak_round_jobs_round` | True | True | `CREATE INDEX ix_soak_round_jobs_round ON public.soak_round_jobs USING btree (run_id, round_number)` |
| `soak_round_jobs_pkey` | True | True | `CREATE UNIQUE INDEX soak_round_jobs_pkey ON public.soak_round_jobs USING btree (run_id, round_number, soldier_id)` |
| `uq_soak_round_job_id` | True | True | `CREATE UNIQUE INDEX uq_soak_round_job_id ON public.soak_round_jobs USING btree (job_id)` |

### `soak_rounds`

| Index | Valid | Ready | Definition |
|---|---|---|---|
| `soak_rounds_pkey` | True | True | `CREATE UNIQUE INDEX soak_rounds_pkey ON public.soak_rounds USING btree (run_id, round_number)` |

### `soak_runs`

| Index | Valid | Ready | Definition |
|---|---|---|---|
| `soak_runs_pkey` | True | True | `CREATE UNIQUE INDEX soak_runs_pkey ON public.soak_runs USING btree (run_id)` |

### `soldier_names`

| Index | Valid | Ready | Definition |
|---|---|---|---|
| `ix_soldier_names_name_lower` | True | True | `CREATE INDEX ix_soldier_names_name_lower ON public.soldier_names USING btree (lower(name))` |
| `soldier_names_pkey` | True | True | `CREATE UNIQUE INDEX soldier_names_pkey ON public.soldier_names USING btree (soldier_name_id)` |
| `uq_soldier_names_soldier_name` | True | True | `CREATE UNIQUE INDEX uq_soldier_names_soldier_name ON public.soldier_names USING btree (soldier_id, name)` |

### `soldier_sources`

| Index | Valid | Ready | Definition |
|---|---|---|---|
| `soldier_sources_pkey` | True | True | `CREATE UNIQUE INDEX soldier_sources_pkey ON public.soldier_sources USING btree (soldier_id, source_type)` |

### `soldier_vehicle_stats`

| Index | Valid | Ready | Definition |
|---|---|---|---|
| `soldier_vehicle_stats_pkey` | True | True | `CREATE UNIQUE INDEX soldier_vehicle_stats_pkey ON public.soldier_vehicle_stats USING btree (soldier_id, vehicle_id)` |

### `soldier_weapon_stats`

| Index | Valid | Ready | Definition |
|---|---|---|---|
| `ix_soldier_weapon_stats_weapon_kills` | True | True | `CREATE INDEX ix_soldier_weapon_stats_weapon_kills ON public.soldier_weapon_stats USING btree (weapon_id, kills DESC, soldier_id)` |
| `soldier_weapon_stats_pkey` | True | True | `CREATE UNIQUE INDEX soldier_weapon_stats_pkey ON public.soldier_weapon_stats USING btree (soldier_id, weapon_id)` |

### `soldiers`

| Index | Valid | Ready | Definition |
|---|---|---|---|
| `ix_soldiers_current_name_lower` | True | True | `CREATE INDEX ix_soldiers_current_name_lower ON public.soldiers USING btree (lower(current_name))` |
| `ix_soldiers_last_seen` | True | True | `CREATE INDEX ix_soldiers_last_seen ON public.soldiers USING btree (last_seen_at)` |
| `soldiers_pkey` | True | True | `CREATE UNIQUE INDEX soldiers_pkey ON public.soldiers USING btree (soldier_id)` |
| `uq_soldiers_persona_platform` | True | True | `CREATE UNIQUE INDEX uq_soldiers_persona_platform ON public.soldiers USING btree (persona_id, platform)` |

### `stage9c_supervision_runs`

| Index | Valid | Ready | Definition |
|---|---|---|---|
| `stage9c_supervision_runs_pkey` | True | True | `CREATE UNIQUE INDEX stage9c_supervision_runs_pkey ON public.stage9c_supervision_runs USING btree (run_id)` |
| `uq_stage9c_one_active_run` | True | True | `CREATE UNIQUE INDEX uq_stage9c_one_active_run ON public.stage9c_supervision_runs USING btree (state) WHERE (state = 'active'::text)` |

### `vehicle_catalog`

| Index | Valid | Ready | Definition |
|---|---|---|---|
| `vehicle_catalog_pkey` | True | True | `CREATE UNIQUE INDEX vehicle_catalog_pkey ON public.vehicle_catalog USING btree (vehicle_id)` |
| `vehicle_catalog_vehicle_guid_key` | True | True | `CREATE UNIQUE INDEX vehicle_catalog_vehicle_guid_key ON public.vehicle_catalog USING btree (vehicle_guid)` |

### `weapon_catalog`

| Index | Valid | Ready | Definition |
|---|---|---|---|
| `weapon_catalog_pkey` | True | True | `CREATE UNIQUE INDEX weapon_catalog_pkey ON public.weapon_catalog USING btree (weapon_id)` |
| `weapon_catalog_weapon_guid_key` | True | True | `CREATE UNIQUE INDEX weapon_catalog_weapon_guid_key ON public.weapon_catalog USING btree (weapon_guid)` |

## Table columns and constraints

### `alembic_version`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `version_num` | character varying | NO | — |

**Constraints:**

- `alembic_version_pkc` (p): `PRIMARY KEY (version_num)`

### `battlelog_profiles`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `profile_id` | bigint | NO | — |
| `battlelog_username` | text | NO | — |
| `battlelog_user_id` | bigint | YES | — |
| `country_code` | character varying | YES | — |
| `country_name` | text | YES | — |
| `access_state` | text | NO | — |
| `last_checked_at` | timestamp with time zone | YES | — |
| `last_success_at` | timestamp with time zone | YES | — |
| `last_error` | text | YES | — |
| `created_at` | timestamp with time zone | NO | `now()` |
| `updated_at` | timestamp with time zone | NO | `now()` |

**Constraints:**

- `battlelog_profiles_access_state_check` (c): `CHECK ((access_state = ANY (ARRAY['public_country'::text, 'public_no_country'::text, 'friends_only'::text, 'not_found'::text, 'error'::text])))`
- `battlelog_profiles_country_upper_check` (c): `CHECK (((country_code IS NULL) OR ((country_code)::text = upper((country_code)::text))))`
- `battlelog_profiles_pkey` (p): `PRIMARY KEY (profile_id)`

### `collection_events`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `event_id` | bigint | NO | — |
| `occurred_at` | timestamp with time zone | NO | `now()` |
| `collector_uuid` | uuid | YES | — |
| `collector_name_snapshot` | text | YES | — |
| `hostname_snapshot` | text | YES | — |
| `egress_key_snapshot` | text | YES | — |
| `job_id` | bigint | YES | — |
| `soldier_id` | bigint | YES | — |
| `persona_id` | bigint | YES | — |
| `platform` | text | YES | — |
| `resource` | text | YES | — |
| `lane` | text | YES | — |
| `event_type` | text | NO | — |
| `attempt_number` | integer | YES | — |
| `result` | text | YES | — |
| `duration_ms` | bigint | YES | — |
| `http_status` | integer | YES | — |
| `error_class` | text | YES | — |
| `error_message` | text | YES | — |
| `lease_token` | uuid | YES | — |
| `metadata` | jsonb | YES | — |

**Constraints:**

- `collection_events_attempt_check` (c): `CHECK (((attempt_number IS NULL) OR (attempt_number >= 0)))`
- `collection_events_collector_uuid_fkey` (f): `FOREIGN KEY (collector_uuid) REFERENCES collectors(collector_uuid) ON DELETE SET NULL`
- `collection_events_duration_check` (c): `CHECK (((duration_ms IS NULL) OR (duration_ms >= 0)))`
- `collection_events_event_type_nonempty` (c): `CHECK ((btrim(event_type) <> ''::text))`
- `collection_events_http_status_check` (c): `CHECK (((http_status IS NULL) OR ((http_status >= 100) AND (http_status <= 599))))`
- `collection_events_lane_check` (c): `CHECK (((lane IS NULL) OR (lane = ANY (ARRAY['background'::text, 'interactive'::text]))))`
- `collection_events_pkey` (p): `PRIMARY KEY (event_id)`
- `collection_events_platform_check` (c): `CHECK (((platform IS NULL) OR (platform = ANY (ARRAY['pc'::text, 'ps4'::text, 'xboxone'::text]))))`
- `collection_events_resource_check` (c): `CHECK (((resource IS NULL) OR (resource = ANY (ARRAY['detailed'::text, 'profile'::text, 'weapons'::text, 'vehicles'::text]))))`
- `collection_events_soldier_id_fkey` (f): `FOREIGN KEY (soldier_id) REFERENCES soldiers(soldier_id) ON DELETE SET NULL`

### `collection_jobs`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `job_id` | bigint | NO | — |
| `soldier_id` | bigint | NO | — |
| `resource` | text | NO | — |
| `lane` | text | NO | — |
| `priority_class` | text | NO | — |
| `reason` | text | NO | — |
| `status` | text | NO | `'pending'::text` |
| `priority_value` | integer | NO | `0` |
| `eligible_at` | timestamp with time zone | NO | `now()` |
| `attempt_count` | integer | NO | `0` |
| `collector_uuid` | uuid | YES | — |
| `lease_token` | uuid | YES | — |
| `claimed_at` | timestamp with time zone | YES | — |
| `started_at` | timestamp with time zone | YES | — |
| `lease_expires_at` | timestamp with time zone | YES | — |
| `last_error_class` | text | YES | — |
| `last_error_at` | timestamp with time zone | YES | — |
| `created_at` | timestamp with time zone | NO | `now()` |
| `updated_at` | timestamp with time zone | NO | `now()` |

**Constraints:**

- `collection_jobs_attempt_count_check` (c): `CHECK ((attempt_count >= 0))`
- `collection_jobs_collector_uuid_fkey` (f): `FOREIGN KEY (collector_uuid) REFERENCES collectors(collector_uuid) ON DELETE SET NULL`
- `collection_jobs_lane_check` (c): `CHECK ((lane = ANY (ARRAY['background'::text, 'interactive'::text])))`
- `collection_jobs_lease_shape_check` (c): `CHECK ((((status = 'pending'::text) AND (collector_uuid IS NULL) AND (lease_token IS NULL) AND (claimed_at IS NULL) AND (started_at IS NULL) AND (lease_expires_at IS NULL)) OR ((status = 'claimed'::text) AND (collector_uuid IS NOT NULL) AND (lease_token IS NOT NULL) AND (claimed_at IS NOT NULL) AND (started_at IS NULL) AND (lease_expires_at IS NOT NULL)) OR ((status = 'running'::text) AND (collector_uuid IS NOT NULL) AND (lease_token IS NOT NULL) AND (claimed_at IS NOT NULL) AND (started_at IS NOT NULL) AND (lease_expires_at IS NOT NULL))))`
- `collection_jobs_pkey` (p): `PRIMARY KEY (job_id)`
- `collection_jobs_priority_class_check` (c): `CHECK ((priority_class = ANY (ARRAY['interactive'::text, 'active'::text, 'recent'::text, 'bootstrap'::text])))`
- `collection_jobs_resource_check` (c): `CHECK ((resource = ANY (ARRAY['detailed'::text, 'profile'::text, 'weapons'::text, 'vehicles'::text])))`
- `collection_jobs_soldier_id_fkey` (f): `FOREIGN KEY (soldier_id) REFERENCES soldiers(soldier_id) ON DELETE CASCADE`
- `collection_jobs_status_check` (c): `CHECK ((status = ANY (ARRAY['pending'::text, 'claimed'::text, 'running'::text])))`
- `uq_collection_jobs_soldier_resource` (u): `UNIQUE (soldier_id, resource)`

### `collection_state`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `soldier_id` | bigint | NO | — |
| `detailed_state` | text | NO | `'never_attempted'::text` |
| `detailed_last_attempt_at` | timestamp with time zone | YES | — |
| `detailed_last_success_at` | timestamp with time zone | YES | — |
| `detailed_next_due_at` | timestamp with time zone | YES | — |
| `detailed_consecutive_failures` | integer | NO | `0` |
| `detailed_last_error_class` | text | YES | — |
| `detailed_last_error_message` | text | YES | — |
| `profile_state` | text | NO | `'never_attempted'::text` |
| `profile_last_attempt_at` | timestamp with time zone | YES | — |
| `profile_last_success_at` | timestamp with time zone | YES | — |
| `profile_next_due_at` | timestamp with time zone | YES | — |
| `profile_consecutive_failures` | integer | NO | `0` |
| `profile_last_error_class` | text | YES | — |
| `profile_last_error_message` | text | YES | — |
| `weapons_state` | text | NO | `'never_attempted'::text` |
| `weapons_last_attempt_at` | timestamp with time zone | YES | — |
| `weapons_last_success_at` | timestamp with time zone | YES | — |
| `weapons_next_due_at` | timestamp with time zone | YES | — |
| `weapons_consecutive_failures` | integer | NO | `0` |
| `weapons_last_error_class` | text | YES | — |
| `weapons_last_error_message` | text | YES | — |
| `vehicles_state` | text | NO | `'never_attempted'::text` |
| `vehicles_last_attempt_at` | timestamp with time zone | YES | — |
| `vehicles_last_success_at` | timestamp with time zone | YES | — |
| `vehicles_next_due_at` | timestamp with time zone | YES | — |
| `vehicles_consecutive_failures` | integer | NO | `0` |
| `vehicles_last_error_class` | text | YES | — |
| `vehicles_last_error_message` | text | YES | — |
| `updated_at` | timestamp with time zone | NO | `now()` |

**Constraints:**

- `collection_state_detailed_failures_check` (c): `CHECK ((detailed_consecutive_failures >= 0))`
- `collection_state_detailed_state_check` (c): `CHECK ((detailed_state = ANY (ARRAY['never_attempted'::text, 'success'::text, 'temporary_failure'::text, 'unavailable'::text])))`
- `collection_state_pkey` (p): `PRIMARY KEY (soldier_id)`
- `collection_state_profile_failures_check` (c): `CHECK ((profile_consecutive_failures >= 0))`
- `collection_state_profile_state_check` (c): `CHECK ((profile_state = ANY (ARRAY['never_attempted'::text, 'success'::text, 'temporary_failure'::text, 'unavailable'::text])))`
- `collection_state_soldier_id_fkey` (f): `FOREIGN KEY (soldier_id) REFERENCES soldiers(soldier_id) ON DELETE CASCADE`
- `collection_state_vehicles_failures_check` (c): `CHECK ((vehicles_consecutive_failures >= 0))`
- `collection_state_vehicles_state_check` (c): `CHECK ((vehicles_state = ANY (ARRAY['never_attempted'::text, 'success'::text, 'temporary_failure'::text, 'unavailable'::text])))`
- `collection_state_weapons_failures_check` (c): `CHECK ((weapons_consecutive_failures >= 0))`
- `collection_state_weapons_state_check` (c): `CHECK ((weapons_state = ANY (ARRAY['never_attempted'::text, 'success'::text, 'temporary_failure'::text, 'unavailable'::text])))`

### `collectors`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `collector_uuid` | uuid | NO | `gen_random_uuid()` |
| `collector_name` | text | NO | — |
| `hostname` | text | NO | — |
| `lane` | text | NO | — |
| `egress_key` | text | NO | — |
| `enabled` | boolean | NO | `true` |
| `drained` | boolean | NO | `false` |
| `software_version` | text | YES | — |
| `started_at` | timestamp with time zone | YES | — |
| `last_heartbeat_at` | timestamp with time zone | YES | — |
| `heartbeat_state` | text | NO | `'unknown'::text` |
| `heartbeat_lost_at` | timestamp with time zone | YES | — |
| `current_job_id` | bigint | YES | — |
| `created_at` | timestamp with time zone | NO | `now()` |
| `updated_at` | timestamp with time zone | NO | `now()` |
| `retired_at` | timestamp with time zone | YES | — |

**Constraints:**

- `collectors_egress_nonempty` (c): `CHECK ((btrim(egress_key) <> ''::text))`
- `collectors_heartbeat_state_check` (c): `CHECK ((heartbeat_state = ANY (ARRAY['unknown'::text, 'healthy'::text, 'lost'::text])))`
- `collectors_hostname_nonempty` (c): `CHECK ((btrim(hostname) <> ''::text))`
- `collectors_lane_check` (c): `CHECK ((lane = ANY (ARRAY['background'::text, 'interactive'::text])))`
- `collectors_name_nonempty` (c): `CHECK ((btrim(collector_name) <> ''::text))`
- `collectors_pkey` (p): `PRIMARY KEY (collector_uuid)`
- `fk_collectors_current_job` (f): `FOREIGN KEY (current_job_id) REFERENCES collection_jobs(job_id) ON DELETE SET NULL`

### `detailed_stats_current`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `soldier_id` | bigint | NO | — |
| `rank` | bigint | YES | — |
| `time_played_seconds` | bigint | YES | — |
| `assault_score` | bigint | YES | — |
| `engineer_score` | bigint | YES | — |
| `support_score` | bigint | YES | — |
| `recon_score` | bigint | YES | — |
| `commander_score` | bigint | YES | — |
| `squad_score` | bigint | YES | — |
| `vehicle_score` | bigint | YES | — |
| `award_score` | bigint | YES | — |
| `unlock_score` | bigint | YES | — |
| `total_score` | bigint | YES | — |
| `combat_score` | bigint | YES | — |
| `conquest_score` | bigint | YES | — |
| `rush_score` | bigint | YES | — |
| `team_deathmatch_score` | bigint | YES | — |
| `domination_score` | bigint | YES | — |
| `obliteration_score` | bigint | YES | — |
| `defuse_score` | bigint | YES | — |
| `capture_the_flag_score` | bigint | YES | — |
| `air_superiority_score` | bigint | YES | — |
| `carrier_assault_score` | bigint | YES | — |
| `chain_link_score` | bigint | YES | — |
| `kills` | bigint | YES | — |
| `deaths` | bigint | YES | — |
| `kill_assists` | bigint | YES | — |
| `wins` | bigint | YES | — |
| `losses` | bigint | YES | — |
| `shots_fired` | bigint | YES | — |
| `shots_hit` | bigint | YES | — |
| `repairs` | bigint | YES | — |
| `revives` | bigint | YES | — |
| `heals` | bigint | YES | — |
| `resupplies` | bigint | YES | — |
| `avenger_kills` | bigint | YES | — |
| `savior_kills` | bigint | YES | — |
| `suppression_assists` | bigint | YES | — |
| `quit_percentage` | numeric | YES | — |
| `flags_captured` | bigint | YES | — |
| `flags_defended` | bigint | YES | — |
| `dogtags_taken` | bigint | YES | — |
| `vehicles_destroyed` | bigint | YES | — |
| `vehicle_damage` | bigint | YES | — |
| `headshots` | bigint | YES | — |
| `longest_headshot` | numeric | YES | — |
| `highest_kill_streak` | bigint | YES | — |
| `nemesis_kills` | bigint | YES | — |
| `highest_nemesis_streak` | bigint | YES | — |
| `source_fetched_at` | timestamp with time zone | NO | — |
| `updated_at` | timestamp with time zone | NO | `now()` |

**Constraints:**

- `detailed_stats_current_pkey` (p): `PRIMARY KEY (soldier_id)`
- `detailed_stats_current_soldier_id_fkey` (f): `FOREIGN KEY (soldier_id) REFERENCES soldiers(soldier_id) ON DELETE CASCADE`

### `detailed_stats_history`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `snapshot_id` | bigint | NO | — |
| `soldier_id` | bigint | NO | — |
| `rank` | bigint | YES | — |
| `time_played_seconds` | bigint | YES | — |
| `assault_score` | bigint | YES | — |
| `engineer_score` | bigint | YES | — |
| `support_score` | bigint | YES | — |
| `recon_score` | bigint | YES | — |
| `commander_score` | bigint | YES | — |
| `squad_score` | bigint | YES | — |
| `vehicle_score` | bigint | YES | — |
| `award_score` | bigint | YES | — |
| `unlock_score` | bigint | YES | — |
| `total_score` | bigint | YES | — |
| `combat_score` | bigint | YES | — |
| `conquest_score` | bigint | YES | — |
| `rush_score` | bigint | YES | — |
| `team_deathmatch_score` | bigint | YES | — |
| `domination_score` | bigint | YES | — |
| `obliteration_score` | bigint | YES | — |
| `defuse_score` | bigint | YES | — |
| `capture_the_flag_score` | bigint | YES | — |
| `air_superiority_score` | bigint | YES | — |
| `carrier_assault_score` | bigint | YES | — |
| `chain_link_score` | bigint | YES | — |
| `kills` | bigint | YES | — |
| `deaths` | bigint | YES | — |
| `kill_assists` | bigint | YES | — |
| `wins` | bigint | YES | — |
| `losses` | bigint | YES | — |
| `shots_fired` | bigint | YES | — |
| `shots_hit` | bigint | YES | — |
| `repairs` | bigint | YES | — |
| `revives` | bigint | YES | — |
| `heals` | bigint | YES | — |
| `resupplies` | bigint | YES | — |
| `avenger_kills` | bigint | YES | — |
| `savior_kills` | bigint | YES | — |
| `suppression_assists` | bigint | YES | — |
| `quit_percentage` | numeric | YES | — |
| `flags_captured` | bigint | YES | — |
| `flags_defended` | bigint | YES | — |
| `dogtags_taken` | bigint | YES | — |
| `vehicles_destroyed` | bigint | YES | — |
| `vehicle_damage` | bigint | YES | — |
| `headshots` | bigint | YES | — |
| `longest_headshot` | numeric | YES | — |
| `highest_kill_streak` | bigint | YES | — |
| `nemesis_kills` | bigint | YES | — |
| `highest_nemesis_streak` | bigint | YES | — |
| `observed_at` | timestamp with time zone | NO | — |

**Constraints:**

- `detailed_stats_history_pkey` (p): `PRIMARY KEY (snapshot_id)`
- `detailed_stats_history_soldier_id_fkey` (f): `FOREIGN KEY (soldier_id) REFERENCES soldiers(soldier_id) ON DELETE CASCADE`

### `discovery_state`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `source_name` | text | NO | — |
| `last_alias_id` | bigint | NO | `'0'::bigint` |
| `last_poll_at` | timestamp with time zone | YES | — |
| `last_success_at` | timestamp with time zone | YES | — |
| `last_error` | text | YES | — |
| `updated_at` | timestamp with time zone | NO | `now()` |

**Constraints:**

- `discovery_state_alias_id_check` (c): `CHECK ((last_alias_id >= 0))`
- `discovery_state_pkey` (p): `PRIMARY KEY (source_name)`

### `outbound_dispatches`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `dispatch_id` | uuid | NO | — |
| `job_id` | bigint | NO | — |
| `attempt_number` | integer | NO | — |
| `resource` | text | NO | — |
| `lease_token` | uuid | NO | — |
| `collector_uuid` | uuid | NO | — |
| `egress_key` | text | NO | — |
| `lane` | text | NO | — |
| `payload_fingerprint` | text | NO | — |
| `admitted_at` | timestamp with time zone | NO | — |
| `phase` | text | NO | `'admitted'::text` |
| `send_marked_at` | timestamp with time zone | YES | — |
| `acknowledged_at` | timestamp with time zone | YES | — |
| `request_ordinal` | integer | NO | `1` |

**Constraints:**

- `outbound_dispatch_ack_after_send` (c): `CHECK (((acknowledged_at IS NULL) OR (acknowledged_at >= send_marked_at)))`
- `outbound_dispatch_attempt_positive` (c): `CHECK (((job_id > 0) AND (attempt_number > 0)))`
- `outbound_dispatch_lane` (c): `CHECK ((lane = ANY (ARRAY['background'::text, 'interactive'::text])))`
- `outbound_dispatch_nonempty` (c): `CHECK (((btrim(egress_key) <> ''::text) AND (btrim(payload_fingerprint) <> ''::text)))`
- `outbound_dispatch_phase` (c): `CHECK ((phase = ANY (ARRAY['admitted'::text, 'may_have_sent'::text, 'acknowledged'::text, 'ambiguous'::text])))`
- `outbound_dispatch_phase_timestamps` (c): `CHECK ((((phase = 'admitted'::text) AND (send_marked_at IS NULL) AND (acknowledged_at IS NULL)) OR ((phase = ANY (ARRAY['may_have_sent'::text, 'ambiguous'::text])) AND (send_marked_at IS NOT NULL) AND (acknowledged_at IS NULL)) OR ((phase = 'acknowledged'::text) AND (send_marked_at IS NOT NULL) AND (acknowledged_at IS NOT NULL))))`
- `outbound_dispatch_request_ordinal_positive` (c): `CHECK ((request_ordinal > 0))`
- `outbound_dispatch_resource` (c): `CHECK ((resource = ANY (ARRAY['detailed'::text, 'profile'::text, 'weapons'::text, 'vehicles'::text])))`
- `outbound_dispatch_send_after_admit` (c): `CHECK (((send_marked_at IS NULL) OR (send_marked_at >= admitted_at)))`
- `outbound_dispatches_pkey` (p): `PRIMARY KEY (dispatch_id)`
- `uq_outbound_dispatch_physical_identity` (u): `UNIQUE (job_id, attempt_number, resource, lease_token, request_ordinal)`

### `player_exclusions`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `platform` | text | NO | — |
| `persona_id` | bigint | NO | — |
| `reason_code` | text | NO | — |
| `private_note` | text | YES | — |
| `created_by` | text | NO | — |
| `created_at` | timestamp with time zone | NO | `now()` |
| `updated_at` | timestamp with time zone | NO | `now()` |
| `active` | boolean | NO | `true` |

**Constraints:**

- `player_exclusions_persona_id_check` (c): `CHECK ((persona_id > 0))`
- `player_exclusions_pkey` (p): `PRIMARY KEY (platform, persona_id)`
- `player_exclusions_platform_check` (c): `CHECK ((platform = ANY (ARRAY['pc'::text, 'ps4'::text, 'xboxone'::text])))`

### `profile_soldiers`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `profile_id` | bigint | NO | — |
| `soldier_id` | bigint | NO | — |
| `first_seen_at` | timestamp with time zone | NO | — |
| `last_seen_at` | timestamp with time zone | NO | — |

**Constraints:**

- `profile_soldiers_pkey` (p): `PRIMARY KEY (profile_id, soldier_id)`
- `profile_soldiers_profile_id_fkey` (f): `FOREIGN KEY (profile_id) REFERENCES battlelog_profiles(profile_id) ON DELETE CASCADE`
- `profile_soldiers_soldier_id_fkey` (f): `FOREIGN KEY (soldier_id) REFERENCES soldiers(soldier_id) ON DELETE CASCADE`

### `request_gates`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `egress_key` | text | NO | — |
| `next_request_at` | timestamp with time zone | NO | — |
| `updated_at` | timestamp with time zone | NO | `now()` |

**Constraints:**

- `request_gates_egress_nonempty` (c): `CHECK ((btrim(egress_key) <> ''::text))`
- `request_gates_pkey` (p): `PRIMARY KEY (egress_key)`

### `soak_round_jobs`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `run_id` | text | NO | — |
| `round_number` | integer | NO | — |
| `soldier_id` | bigint | NO | — |
| `job_id` | bigint | NO | — |
| `outcome` | text | NO | `'pending'::text` |

**Constraints:**

- `soak_job_outcome` (c): `CHECK ((outcome = ANY (ARRAY['pending'::text, 'success'::text, 'failed'::text, 'abandoned'::text])))`
- `soak_job_positive` (c): `CHECK ((job_id > 0))`
- `soak_round_jobs_pkey` (p): `PRIMARY KEY (run_id, round_number, soldier_id)`
- `soak_round_jobs_run_id_round_number_fkey` (f): `FOREIGN KEY (run_id, round_number) REFERENCES soak_rounds(run_id, round_number) ON DELETE RESTRICT`
- `uq_soak_round_job_id` (u): `UNIQUE (job_id)`

### `soak_rounds`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `run_id` | text | NO | — |
| `round_number` | integer | NO | — |
| `eligible_at` | timestamp with time zone | NO | — |
| `state` | text | NO | `'planned'::text` |
| `enqueued_at` | timestamp with time zone | YES | — |
| `completed_at` | timestamp with time zone | YES | — |

**Constraints:**

- `soak_round_number` (c): `CHECK (((round_number >= 1) AND (round_number <= 12)))`
- `soak_round_state` (c): `CHECK ((state = ANY (ARRAY['planned'::text, 'enqueued'::text, 'completed'::text, 'failed'::text])))`
- `soak_round_timestamps` (c): `CHECK ((((state = 'planned'::text) AND (enqueued_at IS NULL) AND (completed_at IS NULL)) OR ((state = 'enqueued'::text) AND (enqueued_at IS NOT NULL) AND (completed_at IS NULL)) OR ((state = ANY (ARRAY['completed'::text, 'failed'::text])) AND (enqueued_at IS NOT NULL))))`
- `soak_rounds_pkey` (p): `PRIMARY KEY (run_id, round_number)`
- `soak_rounds_run_id_fkey` (f): `FOREIGN KEY (run_id) REFERENCES soak_runs(run_id) ON DELETE RESTRICT`

### `soak_runs`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `run_id` | text | NO | — |
| `cohort_digest` | text | NO | — |
| `baseline_event_id` | bigint | NO | — |
| `attempt_ceiling` | integer | NO | — |
| `site_attempt_ceiling` | integer | NO | — |
| `start_at` | timestamp with time zone | YES | — |
| `deadline_at` | timestamp with time zone | YES | — |
| `state` | text | NO | `'prepared'::text` |
| `stop_reason` | text | YES | — |
| `created_at` | timestamp with time zone | NO | `now()` |
| `updated_at` | timestamp with time zone | NO | `now()` |

**Constraints:**

- `soak_run_bounds` (c): `CHECK (((baseline_event_id >= 0) AND (attempt_ceiling > 0) AND (site_attempt_ceiling > 0)))`
- `soak_run_state` (c): `CHECK ((state = ANY (ARRAY['prepared'::text, 'running'::text, 'stopping'::text, 'completed'::text, 'failed'::text, 'stopped'::text])))`
- `soak_run_times` (c): `CHECK ((((start_at IS NULL) AND (deadline_at IS NULL)) OR ((start_at IS NOT NULL) AND (deadline_at > start_at))))`
- `soak_runs_pkey` (p): `PRIMARY KEY (run_id)`

### `soldier_names`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `soldier_name_id` | bigint | NO | — |
| `soldier_id` | bigint | NO | — |
| `name` | text | NO | — |
| `first_seen_at` | timestamp with time zone | NO | — |
| `last_seen_at` | timestamp with time zone | NO | — |

**Constraints:**

- `soldier_names_name_nonempty` (c): `CHECK ((btrim(name) <> ''::text))`
- `soldier_names_pkey` (p): `PRIMARY KEY (soldier_name_id)`
- `soldier_names_soldier_id_fkey` (f): `FOREIGN KEY (soldier_id) REFERENCES soldiers(soldier_id) ON DELETE CASCADE`
- `uq_soldier_names_soldier_name` (u): `UNIQUE (soldier_id, name)`

### `soldier_sources`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `soldier_id` | bigint | NO | — |
| `source_type` | text | NO | — |
| `first_seen_at` | timestamp with time zone | NO | — |
| `last_seen_at` | timestamp with time zone | NO | — |

**Constraints:**

- `soldier_sources_pkey` (p): `PRIMARY KEY (soldier_id, source_type)`
- `soldier_sources_soldier_id_fkey` (f): `FOREIGN KEY (soldier_id) REFERENCES soldiers(soldier_id) ON DELETE CASCADE`
- `soldier_sources_type_check` (c): `CHECK ((source_type = ANY (ARRAY['bf4sw'::text, 'manual'::text])))`

### `soldier_vehicle_stats`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `soldier_id` | bigint | NO | — |
| `vehicle_id` | bigint | NO | — |
| `kills` | bigint | NO | — |
| `time_in_seconds` | bigint | NO | — |
| `destroy_x_in_y` | bigint | YES | — |
| `source_fetched_at` | timestamp with time zone | NO | — |
| `updated_at` | timestamp with time zone | NO | `now()` |

**Constraints:**

- `soldier_vehicle_stats_pkey` (p): `PRIMARY KEY (soldier_id, vehicle_id)`
- `soldier_vehicle_stats_soldier_id_fkey` (f): `FOREIGN KEY (soldier_id) REFERENCES soldiers(soldier_id) ON DELETE CASCADE`
- `soldier_vehicle_stats_vehicle_id_fkey` (f): `FOREIGN KEY (vehicle_id) REFERENCES vehicle_catalog(vehicle_id) ON DELETE CASCADE`

### `soldier_weapon_stats`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `soldier_id` | bigint | NO | — |
| `weapon_id` | bigint | NO | — |
| `kills` | bigint | NO | — |
| `headshots` | bigint | NO | — |
| `shots_fired` | bigint | NO | — |
| `shots_hit` | bigint | NO | — |
| `time_equipped_seconds` | bigint | NO | — |
| `source_fetched_at` | timestamp with time zone | NO | — |
| `updated_at` | timestamp with time zone | NO | `now()` |

**Constraints:**

- `soldier_weapon_stats_pkey` (p): `PRIMARY KEY (soldier_id, weapon_id)`
- `soldier_weapon_stats_soldier_id_fkey` (f): `FOREIGN KEY (soldier_id) REFERENCES soldiers(soldier_id) ON DELETE CASCADE`
- `soldier_weapon_stats_weapon_id_fkey` (f): `FOREIGN KEY (weapon_id) REFERENCES weapon_catalog(weapon_id) ON DELETE CASCADE`

### `soldiers`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `soldier_id` | bigint | NO | — |
| `persona_id` | bigint | NO | — |
| `platform` | text | NO | — |
| `current_name` | text | NO | — |
| `first_seen_at` | timestamp with time zone | NO | — |
| `last_seen_at` | timestamp with time zone | NO | — |
| `created_at` | timestamp with time zone | NO | `now()` |
| `updated_at` | timestamp with time zone | NO | `now()` |

**Constraints:**

- `soldiers_name_nonempty` (c): `CHECK ((btrim(current_name) <> ''::text))`
- `soldiers_pkey` (p): `PRIMARY KEY (soldier_id)`
- `soldiers_platform_check` (c): `CHECK ((platform = ANY (ARRAY['pc'::text, 'ps4'::text, 'xboxone'::text])))`
- `uq_soldiers_persona_platform` (u): `UNIQUE (persona_id, platform)`

### `stage9c_supervision_runs`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `run_id` | uuid | NO | — |
| `state` | text | NO | — |
| `cutover_at` | timestamp with time zone | NO | — |
| `since_event_id` | bigint | NO | — |
| `started_at` | timestamp with time zone | YES | — |
| `deadline_at` | timestamp with time zone | YES | — |
| `watchdog_owner` | uuid | YES | — |
| `watchdog_generation` | bigint | NO | `'0'::bigint` |
| `heartbeat_at` | timestamp with time zone | YES | — |
| `lease_expires_at` | timestamp with time zone | YES | — |
| `abort_at` | timestamp with time zone | YES | — |
| `abort_reason` | text | YES | — |
| `created_at` | timestamp with time zone | NO | `now()` |
| `updated_at` | timestamp with time zone | NO | `now()` |

**Constraints:**

- `stage9c_run_abort_pair` (c): `CHECK ((((abort_at IS NULL) AND (abort_reason IS NULL)) OR ((abort_at IS NOT NULL) AND (abort_reason IS NOT NULL) AND (btrim(abort_reason) <> ''::text))))`
- `stage9c_run_aborted_reason` (c): `CHECK (((state <> 'aborted'::text) OR (abort_at IS NOT NULL)))`
- `stage9c_run_activation_dates` (c): `CHECK (((state = 'prepared'::text) OR ((started_at IS NOT NULL) AND (deadline_at IS NOT NULL))))`
- `stage9c_run_active_lease` (c): `CHECK (((state <> 'active'::text) OR ((watchdog_owner IS NOT NULL) AND (heartbeat_at IS NOT NULL) AND (lease_expires_at IS NOT NULL) AND (lease_expires_at > heartbeat_at))))`
- `stage9c_run_boundary` (c): `CHECK ((since_event_id >= 0))`
- `stage9c_run_generation` (c): `CHECK ((watchdog_generation >= 0))`
- `stage9c_run_six_hour_deadline` (c): `CHECK ((((started_at IS NULL) AND (deadline_at IS NULL)) OR ((started_at IS NOT NULL) AND (deadline_at = (started_at + '06:00:00'::interval)))))`
- `stage9c_run_state` (c): `CHECK ((state = ANY (ARRAY['prepared'::text, 'active'::text, 'aborted'::text, 'completed'::text])))`
- `stage9c_supervision_runs_pkey` (p): `PRIMARY KEY (run_id)`

### `vehicle_catalog`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `vehicle_id` | bigint | NO | — |
| `vehicle_guid` | text | NO | — |
| `name` | text | NO | — |
| `slug` | text | YES | — |
| `category` | text | YES | — |
| `first_seen_at` | timestamp with time zone | NO | — |
| `last_seen_at` | timestamp with time zone | NO | — |

**Constraints:**

- `vehicle_catalog_pkey` (p): `PRIMARY KEY (vehicle_id)`
- `vehicle_catalog_vehicle_guid_key` (u): `UNIQUE (vehicle_guid)`

### `weapon_catalog`

| Column | Type | Nullable | Default |
|---|---|---|---|
| `weapon_id` | bigint | NO | — |
| `weapon_guid` | text | NO | — |
| `name` | text | NO | — |
| `slug` | text | YES | — |
| `category` | text | YES | — |
| `first_seen_at` | timestamp with time zone | NO | — |
| `last_seen_at` | timestamp with time zone | NO | — |

**Constraints:**

- `weapon_catalog_pkey` (p): `PRIMARY KEY (weapon_id)`
- `weapon_catalog_weapon_guid_key` (u): `UNIQUE (weapon_guid)`

## Weapon Top 10 optimization (2026-10-17)

Before this index, the query plan for `WHERE weapon_id = 10` used a **parallel sequential scan** on approximately 11.5 million weapon-stat rows.

The operator initiated the following online index build on the database primary:

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_soldier_weapon_stats_weapon_kills
ON public.soldier_weapon_stats (weapon_id, kills DESC, soldier_id);
```

The website read-only database account cannot create this index. The operator completed the build successfully on `mak-db-02`; subsequent independent inspection through the website database connection verified the index is valid, ready, and live. No Alembic migration is claimed to have been applied for this manual index.

A simple top-10-by-kills query now plans an **Index Only Scan** using this index. Full cold API calls still measured **1.04–3.21 seconds** across four uncached weapon IDs (9, 11, 13, 17), so further SQL-level optimization remains necessary.

**Post-build verification:**

```sql
SELECT i.indisvalid, i.indisready, i.indislive, pg_get_indexdef(i.indexrelid)
FROM pg_index i JOIN pg_class x ON x.oid = i.indexrelid
WHERE x.relname = 'ix_soldier_weapon_stats_weapon_kills';
```

**Schema drift / change-management note:** The live database reports Alembic `0012_manual_verify_api`. Older website documentation describing a D3 scratch-only database or Alembic 0005 is historical, not the current production state. Indexes added manually should be reconciled into the collector-owned migration history before any rebuild or new deployment.

**No database mutations were performed to generate this document.**
