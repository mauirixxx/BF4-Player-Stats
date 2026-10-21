# BF4PS production PostgreSQL schema — live snapshot

Verified against `bf4_playerstats` on `mak-db-02`, 2026-10-21. Alembic revision: `0017_rank_immutable_scores`. This is a read-only catalog snapshot, not a migration or substitute for versioned Alembic source. PostgreSQL types and defaults are transcribed from the live catalog. Do not infer privileges or trigger semantics from the column listing alone.

## Columns (458)


### `alembic_version`

- `version_num` — `varchar` NOT NULL

### `battlelog_profiles`

- `profile_id` — `int8` NOT NULL
- `battlelog_username` — `text` NOT NULL
- `battlelog_user_id` — `int8`
- `country_code` — `varchar`
- `country_name` — `text`
- `access_state` — `text` NOT NULL
- `last_checked_at` — `timestamptz`
- `last_success_at` — `timestamptz`
- `last_error` — `text`
- `created_at` — `timestamptz` NOT NULL DEFAULT `now()`
- `updated_at` — `timestamptz` NOT NULL DEFAULT `now()`

### `collection_events`

- `event_id` — `int8` NOT NULL
- `occurred_at` — `timestamptz` NOT NULL DEFAULT `now()`
- `collector_uuid` — `uuid`
- `collector_name_snapshot` — `text`
- `hostname_snapshot` — `text`
- `egress_key_snapshot` — `text`
- `job_id` — `int8`
- `soldier_id` — `int8`
- `persona_id` — `int8`
- `platform` — `text`
- `resource` — `text`
- `lane` — `text`
- `event_type` — `text` NOT NULL
- `attempt_number` — `int4`
- `result` — `text`
- `duration_ms` — `int8`
- `http_status` — `int4`
- `error_class` — `text`
- `error_message` — `text`
- `lease_token` — `uuid`
- `metadata` — `jsonb`

### `collection_jobs`

- `job_id` — `int8` NOT NULL
- `soldier_id` — `int8` NOT NULL
- `resource` — `text` NOT NULL
- `lane` — `text` NOT NULL
- `priority_class` — `text` NOT NULL
- `reason` — `text` NOT NULL
- `status` — `text` NOT NULL DEFAULT `'pending'::text`
- `priority_value` — `int4` NOT NULL DEFAULT `0`
- `eligible_at` — `timestamptz` NOT NULL DEFAULT `now()`
- `attempt_count` — `int4` NOT NULL DEFAULT `0`
- `collector_uuid` — `uuid`
- `lease_token` — `uuid`
- `claimed_at` — `timestamptz`
- `started_at` — `timestamptz`
- `lease_expires_at` — `timestamptz`
- `last_error_class` — `text`
- `last_error_at` — `timestamptz`
- `created_at` — `timestamptz` NOT NULL DEFAULT `now()`
- `updated_at` — `timestamptz` NOT NULL DEFAULT `now()`

### `collection_state`

- `soldier_id` — `int8` NOT NULL
- `detailed_state` — `text` NOT NULL DEFAULT `'never_attempted'::text`
- `detailed_last_attempt_at` — `timestamptz`
- `detailed_last_success_at` — `timestamptz`
- `detailed_next_due_at` — `timestamptz`
- `detailed_consecutive_failures` — `int4` NOT NULL DEFAULT `0`
- `detailed_last_error_class` — `text`
- `detailed_last_error_message` — `text`
- `profile_state` — `text` NOT NULL DEFAULT `'never_attempted'::text`
- `profile_last_attempt_at` — `timestamptz`
- `profile_last_success_at` — `timestamptz`
- `profile_next_due_at` — `timestamptz`
- `profile_consecutive_failures` — `int4` NOT NULL DEFAULT `0`
- `profile_last_error_class` — `text`
- `profile_last_error_message` — `text`
- `weapons_state` — `text` NOT NULL DEFAULT `'never_attempted'::text`
- `weapons_last_attempt_at` — `timestamptz`
- `weapons_last_success_at` — `timestamptz`
- `weapons_next_due_at` — `timestamptz`
- `weapons_consecutive_failures` — `int4` NOT NULL DEFAULT `0`
- `weapons_last_error_class` — `text`
- `weapons_last_error_message` — `text`
- `vehicles_state` — `text` NOT NULL DEFAULT `'never_attempted'::text`
- `vehicles_last_attempt_at` — `timestamptz`
- `vehicles_last_success_at` — `timestamptz`
- `vehicles_next_due_at` — `timestamptz`
- `vehicles_consecutive_failures` — `int4` NOT NULL DEFAULT `0`
- `vehicles_last_error_class` — `text`
- `vehicles_last_error_message` — `text`
- `updated_at` — `timestamptz` NOT NULL DEFAULT `now()`

### `collectors`

- `collector_uuid` — `uuid` NOT NULL DEFAULT `gen_random_uuid()`
- `collector_name` — `text` NOT NULL
- `hostname` — `text` NOT NULL
- `lane` — `text` NOT NULL
- `egress_key` — `text` NOT NULL
- `enabled` — `bool` NOT NULL DEFAULT `true`
- `drained` — `bool` NOT NULL DEFAULT `false`
- `software_version` — `text`
- `started_at` — `timestamptz`
- `last_heartbeat_at` — `timestamptz`
- `heartbeat_state` — `text` NOT NULL DEFAULT `'unknown'::text`
- `heartbeat_lost_at` — `timestamptz`
- `current_job_id` — `int8`
- `created_at` — `timestamptz` NOT NULL DEFAULT `now()`
- `updated_at` — `timestamptz` NOT NULL DEFAULT `now()`
- `retired_at` — `timestamptz`

### `detailed_stats_current`

- `soldier_id` — `int8` NOT NULL
- `rank` — `int8`
- `time_played_seconds` — `int8`
- `assault_score` — `int8`
- `engineer_score` — `int8`
- `support_score` — `int8`
- `recon_score` — `int8`
- `commander_score` — `int8`
- `squad_score` — `int8`
- `vehicle_score` — `int8`
- `award_score` — `int8`
- `unlock_score` — `int8`
- `total_score` — `int8`
- `combat_score` — `int8`
- `conquest_score` — `int8`
- `rush_score` — `int8`
- `team_deathmatch_score` — `int8`
- `domination_score` — `int8`
- `obliteration_score` — `int8`
- `defuse_score` — `int8`
- `capture_the_flag_score` — `int8`
- `air_superiority_score` — `int8`
- `carrier_assault_score` — `int8`
- `chain_link_score` — `int8`
- `kills` — `int8`
- `deaths` — `int8`
- `kill_assists` — `int8`
- `wins` — `int8`
- `losses` — `int8`
- `shots_fired` — `int8`
- `shots_hit` — `int8`
- `repairs` — `int8`
- `revives` — `int8`
- `heals` — `int8`
- `resupplies` — `int8`
- `avenger_kills` — `int8`
- `savior_kills` — `int8`
- `suppression_assists` — `int8`
- `quit_percentage` — `numeric`
- `flags_captured` — `int8`
- `flags_defended` — `int8`
- `dogtags_taken` — `int8`
- `vehicles_destroyed` — `int8`
- `vehicle_damage` — `int8`
- `headshots` — `int8`
- `longest_headshot` — `numeric`
- `highest_kill_streak` — `int8`
- `nemesis_kills` — `int8`
- `highest_nemesis_streak` — `int8`
- `source_fetched_at` — `timestamptz` NOT NULL
- `updated_at` — `timestamptz` NOT NULL DEFAULT `now()`

### `detailed_stats_history`

- `snapshot_id` — `int8` NOT NULL
- `soldier_id` — `int8` NOT NULL
- `rank` — `int8`
- `time_played_seconds` — `int8`
- `assault_score` — `int8`
- `engineer_score` — `int8`
- `support_score` — `int8`
- `recon_score` — `int8`
- `commander_score` — `int8`
- `squad_score` — `int8`
- `vehicle_score` — `int8`
- `award_score` — `int8`
- `unlock_score` — `int8`
- `total_score` — `int8`
- `combat_score` — `int8`
- `conquest_score` — `int8`
- `rush_score` — `int8`
- `team_deathmatch_score` — `int8`
- `domination_score` — `int8`
- `obliteration_score` — `int8`
- `defuse_score` — `int8`
- `capture_the_flag_score` — `int8`
- `air_superiority_score` — `int8`
- `carrier_assault_score` — `int8`
- `chain_link_score` — `int8`
- `kills` — `int8`
- `deaths` — `int8`
- `kill_assists` — `int8`
- `wins` — `int8`
- `losses` — `int8`
- `shots_fired` — `int8`
- `shots_hit` — `int8`
- `repairs` — `int8`
- `revives` — `int8`
- `heals` — `int8`
- `resupplies` — `int8`
- `avenger_kills` — `int8`
- `savior_kills` — `int8`
- `suppression_assists` — `int8`
- `quit_percentage` — `numeric`
- `flags_captured` — `int8`
- `flags_defended` — `int8`
- `dogtags_taken` — `int8`
- `vehicles_destroyed` — `int8`
- `vehicle_damage` — `int8`
- `headshots` — `int8`
- `longest_headshot` — `numeric`
- `highest_kill_streak` — `int8`
- `nemesis_kills` — `int8`
- `highest_nemesis_streak` — `int8`
- `observed_at` — `timestamptz` NOT NULL

### `discovery_state`

- `source_name` — `text` NOT NULL
- `last_alias_id` — `int8` NOT NULL DEFAULT `'0'::bigint`
- `last_poll_at` — `timestamptz`
- `last_success_at` — `timestamptz`
- `last_error` — `text`
- `updated_at` — `timestamptz` NOT NULL DEFAULT `now()`

### `equipment_population`

- `kind` — `text` NOT NULL
- `item_id` — `int8` NOT NULL
- `platform` — `text` NOT NULL
- `population` — `int8` NOT NULL

### `equipment_rank_generations`

- `generation_id` — `int8` NOT NULL
- `kind` — `text` NOT NULL
- `item_id` — `int8` NOT NULL
- `platform` — `text` NOT NULL
- `metric` — `text` NOT NULL
- `status` — `text` NOT NULL DEFAULT `'building'::text`
- `row_count` — `int8`
- `input_max_fetched_at` — `timestamptz`
- `created_at` — `timestamptz` NOT NULL DEFAULT `now()`
- `completed_at` — `timestamptz`
- `input_scope_version` — `int8`
- `snapshot_format` — `int2` NOT NULL DEFAULT `'0'::smallint`

### `equipment_rank_published`

- `kind` — `text` NOT NULL
- `item_id` — `int8` NOT NULL
- `platform` — `text` NOT NULL
- `metric` — `text` NOT NULL
- `generation_id` — `int8` NOT NULL
- `published_at` — `timestamptz` NOT NULL DEFAULT `now()`

### `equipment_rank_rows`

- `generation_id` — `int8` NOT NULL
- `soldier_id` — `int8` NOT NULL
- `rank` — `int8` NOT NULL
- `position` — `int8` NOT NULL
- `snapshot_kills` — `int8`
- `snapshot_kpm` — `numeric`
- `snapshot_accuracy` — `numeric`
- `snapshot_source_fetched_at` — `timestamptz`

### `equipment_rank_scope_versions`

- `kind` — `text` NOT NULL
- `item_id` — `int8` NOT NULL
- `platform` — `text` NOT NULL
- `version` — `int8` NOT NULL DEFAULT `'0'::bigint`
- `changed_at` — `timestamptz` NOT NULL DEFAULT `now()`

### `manual_collection_requests`

- `request_id` — `int8` NOT NULL
- `soldier_id` — `int8` NOT NULL
- `request_kind` — `text` NOT NULL
- `status` — `text` NOT NULL DEFAULT `'accepted'::text`
- `requested_at` — `timestamptz` NOT NULL DEFAULT `now()`
- `completed_at` — `timestamptz`
- `status_detail` — `text`

### `manual_request_cooldowns`

- `soldier_id` — `int8` NOT NULL
- `last_accepted_at` — `timestamptz` NOT NULL
- `last_request_id` — `int8` NOT NULL

### `manual_soldier_verifications`

- `verification_id` — `int8` NOT NULL
- `persona_id` — `int8` NOT NULL
- `platform` — `text` NOT NULL
- `submitted_url` — `text` NOT NULL
- `status` — `text` NOT NULL DEFAULT `'pending'::text`
- `submitted_at` — `timestamptz` NOT NULL DEFAULT `now()`
- `claimed_at` — `timestamptz`
- `lease_expires_at` — `timestamptz`
- `collector_uuid` — `uuid`
- `attempt_count` — `int4` NOT NULL DEFAULT `0`
- `soldier_id` — `int8`
- `last_error` — `text`

### `outbound_dispatches`

- `dispatch_id` — `uuid` NOT NULL
- `job_id` — `int8` NOT NULL
- `attempt_number` — `int4` NOT NULL
- `resource` — `text` NOT NULL
- `lease_token` — `uuid` NOT NULL
- `collector_uuid` — `uuid` NOT NULL
- `egress_key` — `text` NOT NULL
- `lane` — `text` NOT NULL
- `payload_fingerprint` — `text` NOT NULL
- `admitted_at` — `timestamptz` NOT NULL
- `phase` — `text` NOT NULL DEFAULT `'admitted'::text`
- `send_marked_at` — `timestamptz`
- `acknowledged_at` — `timestamptz`
- `request_ordinal` — `int4` NOT NULL DEFAULT `1`

### `platoon_requests`

- `platoon_id` — `int8` NOT NULL
- `requested_at` — `timestamptz` NOT NULL DEFAULT `now()`
- `last_attempt_at` — `timestamptz`
- `next_attempt_at` — `timestamptz` NOT NULL DEFAULT `now()`
- `attempts` — `int4` NOT NULL DEFAULT `0`
- `status` — `text` NOT NULL DEFAULT `'pending'::text`
- `last_error` — `text`

### `platoon_roster_accounts`

- `platoon_id` — `int8` NOT NULL
- `battlelog_account_id` — `int8` NOT NULL
- `account_name` — `text`
- `role` — `text` NOT NULL
- `joined_at` — `timestamptz`
- `first_seen_at` — `timestamptz` NOT NULL DEFAULT `now()`
- `last_seen_at` — `timestamptz` NOT NULL DEFAULT `now()`
- `is_current` — `bool` NOT NULL DEFAULT `true`

### `platoon_roster_personas`

- `platoon_id` — `int8` NOT NULL
- `battlelog_account_id` — `int8` NOT NULL
- `battlelog_platform_code` — `int4` NOT NULL
- `persona_id` — `int8` NOT NULL
- `persona_name` — `text` NOT NULL
- `platform_family` — `text` NOT NULL
- `last_seen_at` — `timestamptz` NOT NULL DEFAULT `now()`
- `is_current` — `bool` NOT NULL DEFAULT `true`

### `platoon_soldier_discovery`

- `soldier_id` — `int8` NOT NULL
- `status` — `text` NOT NULL DEFAULT `'pending'::text`
- `attempts` — `int4` NOT NULL DEFAULT `0`
- `next_attempt_at` — `timestamptz` NOT NULL DEFAULT `now()`
- `last_checked_at` — `timestamptz`
- `linked_platoon_id` — `int8`
- `displayed_tag` — `text`
- `last_error` — `text`
- `created_at` — `timestamptz` NOT NULL DEFAULT `now()`

### `platoon_sync_runs`

- `sync_id` — `int8` NOT NULL
- `platoon_id` — `int8` NOT NULL
- `started_at` — `timestamptz` NOT NULL DEFAULT `now()`
- `completed_at` — `timestamptz`
- `success` — `bool`
- `account_count` — `int4`
- `bf4_platform_records` — `int4`
- `response_bytes` — `int4`
- `error` — `text`

### `platoon_work_leases`

- `platoon_id` — `int8` NOT NULL
- `claim_token` — `uuid` NOT NULL
- `claimed_by` — `text` NOT NULL
- `lease_until` — `timestamptz` NOT NULL
- `claimed_at` — `timestamptz` NOT NULL DEFAULT `now()`
- `work_kind` — `text` NOT NULL

### `platoons`

- `platoon_id` — `int8` NOT NULL
- `name` — `text` NOT NULL
- `tag` — `text` NOT NULL
- `official_member_count` — `int4` NOT NULL
- `battlelog_created_at` — `timestamptz`
- `first_seen_at` — `timestamptz` NOT NULL DEFAULT `now()`
- `last_checked_at` — `timestamptz`
- `last_success_at` — `timestamptz`
- `last_error` — `text`
- `next_refresh_at` — `timestamptz`
- `discovery_source` — `text` NOT NULL DEFAULT `'manual'::text`
- `emblem_path` — `text`
- `website_url` — `text`

### `player_exclusion_audit`

- `audit_id` — `int8` NOT NULL
- `platform` — `text` NOT NULL
- `persona_id` — `int8` NOT NULL
- `action` — `text` NOT NULL
- `actor` — `text` NOT NULL
- `reason_code` — `text`
- `private_note` — `text`
- `occurred_at` — `timestamptz` NOT NULL DEFAULT `now()`

### `player_exclusions`

- `platform` — `text` NOT NULL
- `persona_id` — `int8` NOT NULL
- `reason_code` — `text` NOT NULL
- `private_note` — `text`
- `created_by` — `text` NOT NULL
- `created_at` — `timestamptz` NOT NULL DEFAULT `now()`
- `updated_at` — `timestamptz` NOT NULL DEFAULT `now()`
- `active` — `bool` NOT NULL DEFAULT `true`

### `profile_soldiers`

- `profile_id` — `int8` NOT NULL
- `soldier_id` — `int8` NOT NULL
- `first_seen_at` — `timestamptz` NOT NULL
- `last_seen_at` — `timestamptz` NOT NULL

### `request_gates`

- `egress_key` — `text` NOT NULL
- `next_request_at` — `timestamptz` NOT NULL
- `updated_at` — `timestamptz` NOT NULL DEFAULT `now()`

### `runtime_budgets`

- `singleton` — `bool` NOT NULL DEFAULT `true`
- `physical_dispatches_per_hour` — `int4` NOT NULL
- `background_slots_per_hour` — `int4` NOT NULL
- `updated_at` — `timestamptz` NOT NULL DEFAULT `now()`

### `soak_round_jobs`

- `run_id` — `text` NOT NULL
- `round_number` — `int4` NOT NULL
- `soldier_id` — `int8` NOT NULL
- `job_id` — `int8` NOT NULL
- `outcome` — `text` NOT NULL DEFAULT `'pending'::text`

### `soak_rounds`

- `run_id` — `text` NOT NULL
- `round_number` — `int4` NOT NULL
- `eligible_at` — `timestamptz` NOT NULL
- `state` — `text` NOT NULL DEFAULT `'planned'::text`
- `enqueued_at` — `timestamptz`
- `completed_at` — `timestamptz`

### `soak_runs`

- `run_id` — `text` NOT NULL
- `cohort_digest` — `text` NOT NULL
- `baseline_event_id` — `int8` NOT NULL
- `attempt_ceiling` — `int4` NOT NULL
- `site_attempt_ceiling` — `int4` NOT NULL
- `start_at` — `timestamptz`
- `deadline_at` — `timestamptz`
- `state` — `text` NOT NULL DEFAULT `'prepared'::text`
- `stop_reason` — `text`
- `created_at` — `timestamptz` NOT NULL DEFAULT `now()`
- `updated_at` — `timestamptz` NOT NULL DEFAULT `now()`

### `soldier_names`

- `soldier_name_id` — `int8` NOT NULL
- `soldier_id` — `int8` NOT NULL
- `name` — `text` NOT NULL
- `first_seen_at` — `timestamptz` NOT NULL
- `last_seen_at` — `timestamptz` NOT NULL

### `soldier_sources`

- `soldier_id` — `int8` NOT NULL
- `source_type` — `text` NOT NULL
- `first_seen_at` — `timestamptz` NOT NULL
- `last_seen_at` — `timestamptz` NOT NULL

### `soldier_vehicle_stats`

- `soldier_id` — `int8` NOT NULL
- `vehicle_id` — `int8` NOT NULL
- `kills` — `int8` NOT NULL
- `time_in_seconds` — `int8` NOT NULL
- `destroy_x_in_y` — `int8`
- `source_fetched_at` — `timestamptz` NOT NULL
- `updated_at` — `timestamptz` NOT NULL DEFAULT `now()`

### `soldier_weapon_stats`

- `soldier_id` — `int8` NOT NULL
- `weapon_id` — `int8` NOT NULL
- `kills` — `int8` NOT NULL
- `headshots` — `int8` NOT NULL
- `shots_fired` — `int8` NOT NULL
- `shots_hit` — `int8` NOT NULL
- `time_equipped_seconds` — `int8` NOT NULL
- `source_fetched_at` — `timestamptz` NOT NULL
- `updated_at` — `timestamptz` NOT NULL DEFAULT `now()`

### `soldiers`

- `soldier_id` — `int8` NOT NULL
- `persona_id` — `int8` NOT NULL
- `platform` — `text` NOT NULL
- `current_name` — `text` NOT NULL
- `first_seen_at` — `timestamptz` NOT NULL
- `last_seen_at` — `timestamptz` NOT NULL
- `created_at` — `timestamptz` NOT NULL DEFAULT `now()`
- `updated_at` — `timestamptz` NOT NULL DEFAULT `now()`

### `stage9c_supervision_runs`

- `run_id` — `uuid` NOT NULL
- `state` — `text` NOT NULL
- `cutover_at` — `timestamptz` NOT NULL
- `since_event_id` — `int8` NOT NULL
- `started_at` — `timestamptz`
- `deadline_at` — `timestamptz`
- `watchdog_owner` — `uuid`
- `watchdog_generation` — `int8` NOT NULL DEFAULT `'0'::bigint`
- `heartbeat_at` — `timestamptz`
- `lease_expires_at` — `timestamptz`
- `abort_at` — `timestamptz`
- `abort_reason` — `text`
- `created_at` — `timestamptz` NOT NULL DEFAULT `now()`
- `updated_at` — `timestamptz` NOT NULL DEFAULT `now()`

### `vehicle_catalog`

- `vehicle_id` — `int8` NOT NULL
- `vehicle_guid` — `text` NOT NULL
- `name` — `text` NOT NULL
- `slug` — `text`
- `category` — `text`
- `first_seen_at` — `timestamptz` NOT NULL
- `last_seen_at` — `timestamptz` NOT NULL

### `vehicle_leaderboard_metrics`

- `soldier_id` — `int8` NOT NULL
- `vehicle_id` — `int8` NOT NULL
- `kills` — `int8` NOT NULL
- `kpm` — `numeric`
- `source_fetched_at` — `timestamptz` NOT NULL

### `weapon_catalog`

- `weapon_id` — `int8` NOT NULL
- `weapon_guid` — `text` NOT NULL
- `name` — `text` NOT NULL
- `slug` — `text`
- `category` — `text`
- `first_seen_at` — `timestamptz` NOT NULL
- `last_seen_at` — `timestamptz` NOT NULL

### `weapon_leaderboard_metrics`

- `soldier_id` — `int8` NOT NULL
- `weapon_id` — `int8` NOT NULL
- `kills` — `int8` NOT NULL
- `kpm` — `numeric`
- `accuracy` — `numeric`
- `source_fetched_at` — `timestamptz` NOT NULL

## Indexes (94)


### `alembic_version`

- `alembic_version_pkc`: CREATE UNIQUE INDEX alembic_version_pkc ON public.alembic_version USING btree (version_num)

### `battlelog_profiles`

- `battlelog_profiles_pkey`: CREATE UNIQUE INDEX battlelog_profiles_pkey ON public.battlelog_profiles USING btree (profile_id)
- `uq_battlelog_profiles_username_lower`: CREATE UNIQUE INDEX uq_battlelog_profiles_username_lower ON public.battlelog_profiles USING btree (lower(battlelog_username))

### `collection_events`

- `collection_events_pkey`: CREATE UNIQUE INDEX collection_events_pkey ON public.collection_events USING btree (event_id)
- `ix_collection_events_collector_time`: CREATE INDEX ix_collection_events_collector_time ON public.collection_events USING btree (collector_uuid, occurred_at DESC)
- `ix_collection_events_http_errors`: CREATE INDEX ix_collection_events_http_errors ON public.collection_events USING btree (http_status, occurred_at DESC) WHERE (http_status IS NOT NULL)
- `ix_collection_events_job`: CREATE INDEX ix_collection_events_job ON public.collection_events USING btree (job_id, occurred_at) WHERE (job_id IS NOT NULL)
- `ix_collection_events_persona_time`: CREATE INDEX ix_collection_events_persona_time ON public.collection_events USING btree (platform, persona_id, occurred_at DESC) WHERE (persona_id IS NOT NULL)
- `ix_collection_events_soldier_time`: CREATE INDEX ix_collection_events_soldier_time ON public.collection_events USING btree (soldier_id, occurred_at DESC) WHERE (soldier_id IS NOT NULL)
- `ix_collection_events_time`: CREATE INDEX ix_collection_events_time ON public.collection_events USING btree (occurred_at DESC)
- `ix_collection_events_type_time`: CREATE INDEX ix_collection_events_type_time ON public.collection_events USING btree (event_type, occurred_at DESC)

### `collection_jobs`

- `collection_jobs_pkey`: CREATE UNIQUE INDEX collection_jobs_pkey ON public.collection_jobs USING btree (job_id)
- `ix_collection_jobs_claim`: CREATE INDEX ix_collection_jobs_claim ON public.collection_jobs USING btree (lane, priority_class, priority_value DESC, eligible_at, created_at, job_id) WHERE (status = 'pending'::text)
- `ix_collection_jobs_collector`: CREATE INDEX ix_collection_jobs_collector ON public.collection_jobs USING btree (collector_uuid) WHERE (collector_uuid IS NOT NULL)
- `ix_collection_jobs_expired_lease`: CREATE INDEX ix_collection_jobs_expired_lease ON public.collection_jobs USING btree (lease_expires_at, job_id) WHERE (status = ANY (ARRAY['claimed'::text, 'running'::text]))
- `uq_collection_jobs_soldier_resource`: CREATE UNIQUE INDEX uq_collection_jobs_soldier_resource ON public.collection_jobs USING btree (soldier_id, resource)

### `collection_state`

- `collection_state_pkey`: CREATE UNIQUE INDEX collection_state_pkey ON public.collection_state USING btree (soldier_id)
- `ix_collection_state_detailed_due`: CREATE INDEX ix_collection_state_detailed_due ON public.collection_state USING btree (detailed_next_due_at) WHERE (detailed_next_due_at IS NOT NULL)
- `ix_collection_state_profile_due`: CREATE INDEX ix_collection_state_profile_due ON public.collection_state USING btree (profile_next_due_at) WHERE (profile_next_due_at IS NOT NULL)
- `ix_collection_state_vehicles_due`: CREATE INDEX ix_collection_state_vehicles_due ON public.collection_state USING btree (vehicles_next_due_at) WHERE (vehicles_next_due_at IS NOT NULL)
- `ix_collection_state_weapons_due`: CREATE INDEX ix_collection_state_weapons_due ON public.collection_state USING btree (weapons_next_due_at) WHERE (weapons_next_due_at IS NOT NULL)

### `collectors`

- `collectors_pkey`: CREATE UNIQUE INDEX collectors_pkey ON public.collectors USING btree (collector_uuid)
- `ix_collectors_egress`: CREATE INDEX ix_collectors_egress ON public.collectors USING btree (egress_key) WHERE (retired_at IS NULL)
- `ix_collectors_heartbeat`: CREATE INDEX ix_collectors_heartbeat ON public.collectors USING btree (heartbeat_state, last_heartbeat_at) WHERE (retired_at IS NULL)
- `uq_collectors_active_name`: CREATE UNIQUE INDEX uq_collectors_active_name ON public.collectors USING btree (lower(collector_name)) WHERE (retired_at IS NULL)

### `detailed_stats_current`

- `detailed_stats_current_pkey`: CREATE UNIQUE INDEX detailed_stats_current_pkey ON public.detailed_stats_current USING btree (soldier_id)

### `detailed_stats_history`

- `detailed_stats_history_pkey`: CREATE UNIQUE INDEX detailed_stats_history_pkey ON public.detailed_stats_history USING btree (snapshot_id)
- `ix_detailed_history_soldier_observed`: CREATE INDEX ix_detailed_history_soldier_observed ON public.detailed_stats_history USING btree (soldier_id, observed_at DESC)

### `discovery_state`

- `discovery_state_pkey`: CREATE UNIQUE INDEX discovery_state_pkey ON public.discovery_state USING btree (source_name)

### `equipment_population`

- `equipment_population_pkey`: CREATE UNIQUE INDEX equipment_population_pkey ON public.equipment_population USING btree (kind, item_id, platform)

### `equipment_rank_generations`

- `equipment_rank_generations_pkey`: CREATE UNIQUE INDEX equipment_rank_generations_pkey ON public.equipment_rank_generations USING btree (generation_id)

### `equipment_rank_published`

- `equipment_rank_published_pkey`: CREATE UNIQUE INDEX equipment_rank_published_pkey ON public.equipment_rank_published USING btree (kind, item_id, platform, metric)

### `equipment_rank_rows`

- `equipment_rank_rows_pkey`: CREATE UNIQUE INDEX equipment_rank_rows_pkey ON public.equipment_rank_rows USING btree (generation_id, soldier_id)
- `ix_equipment_rank_rows_soldier`: CREATE INDEX ix_equipment_rank_rows_soldier ON public.equipment_rank_rows USING btree (soldier_id, generation_id)
- `uq_equipment_rank_generation_position`: CREATE UNIQUE INDEX uq_equipment_rank_generation_position ON public.equipment_rank_rows USING btree (generation_id, "position")

### `equipment_rank_scope_versions`

- `equipment_rank_scope_versions_pkey`: CREATE UNIQUE INDEX equipment_rank_scope_versions_pkey ON public.equipment_rank_scope_versions USING btree (kind, item_id, platform)

### `manual_collection_requests`

- `ix_manual_requests_soldier_time`: CREATE INDEX ix_manual_requests_soldier_time ON public.manual_collection_requests USING btree (soldier_id, requested_at DESC)
- `ix_manual_requests_status`: CREATE INDEX ix_manual_requests_status ON public.manual_collection_requests USING btree (status, requested_at)
- `manual_collection_requests_pkey`: CREATE UNIQUE INDEX manual_collection_requests_pkey ON public.manual_collection_requests USING btree (request_id)

### `manual_request_cooldowns`

- `manual_request_cooldowns_pkey`: CREATE UNIQUE INDEX manual_request_cooldowns_pkey ON public.manual_request_cooldowns USING btree (soldier_id)

### `manual_soldier_verifications`

- `ix_manual_verify_claim`: CREATE INDEX ix_manual_verify_claim ON public.manual_soldier_verifications USING btree (status, submitted_at)
- `manual_soldier_verifications_pkey`: CREATE UNIQUE INDEX manual_soldier_verifications_pkey ON public.manual_soldier_verifications USING btree (verification_id)
- `uq_manual_verify_identity`: CREATE UNIQUE INDEX uq_manual_verify_identity ON public.manual_soldier_verifications USING btree (persona_id, platform)

### `outbound_dispatches`

- `ix_outbound_dispatch_admitted_at`: CREATE INDEX ix_outbound_dispatch_admitted_at ON public.outbound_dispatches USING btree (admitted_at)
- `ix_outbound_dispatch_background_admitted`: CREATE INDEX ix_outbound_dispatch_background_admitted ON public.outbound_dispatches USING btree (admitted_at) WHERE (lane = 'background'::text)
- `ix_outbound_dispatch_egress_admitted`: CREATE INDEX ix_outbound_dispatch_egress_admitted ON public.outbound_dispatches USING btree (egress_key, admitted_at)
- `outbound_dispatches_pkey`: CREATE UNIQUE INDEX outbound_dispatches_pkey ON public.outbound_dispatches USING btree (dispatch_id)
- `uq_outbound_dispatch_physical_identity`: CREATE UNIQUE INDEX uq_outbound_dispatch_physical_identity ON public.outbound_dispatches USING btree (job_id, attempt_number, resource, lease_token, request_ordinal)

### `platoon_requests`

- `platoon_requests_pkey`: CREATE UNIQUE INDEX platoon_requests_pkey ON public.platoon_requests USING btree (platoon_id)

### `platoon_roster_accounts`

- `ix_platoon_accounts_account`: CREATE INDEX ix_platoon_accounts_account ON public.platoon_roster_accounts USING btree (battlelog_account_id) WHERE is_current
- `platoon_roster_accounts_pkey`: CREATE UNIQUE INDEX platoon_roster_accounts_pkey ON public.platoon_roster_accounts USING btree (platoon_id, battlelog_account_id)

### `platoon_roster_personas`

- `ix_platoon_personas_identity`: CREATE INDEX ix_platoon_personas_identity ON public.platoon_roster_personas USING btree (platform_family, persona_id) WHERE is_current
- `platoon_roster_personas_pkey`: CREATE UNIQUE INDEX platoon_roster_personas_pkey ON public.platoon_roster_personas USING btree (platoon_id, battlelog_account_id, battlelog_platform_code, persona_id)

### `platoon_soldier_discovery`

- `ix_platoon_soldier_discovery_due`: CREATE INDEX ix_platoon_soldier_discovery_due ON public.platoon_soldier_discovery USING btree (next_attempt_at) WHERE (status = ANY (ARRAY['pending'::text, 'failed'::text]))
- `platoon_soldier_discovery_pkey`: CREATE UNIQUE INDEX platoon_soldier_discovery_pkey ON public.platoon_soldier_discovery USING btree (soldier_id)

### `platoon_sync_runs`

- `platoon_sync_runs_pkey`: CREATE UNIQUE INDEX platoon_sync_runs_pkey ON public.platoon_sync_runs USING btree (sync_id)

### `platoon_work_leases`

- `platoon_work_leases_expiry_idx`: CREATE INDEX platoon_work_leases_expiry_idx ON public.platoon_work_leases USING btree (lease_until)
- `platoon_work_leases_pkey`: CREATE UNIQUE INDEX platoon_work_leases_pkey ON public.platoon_work_leases USING btree (platoon_id)

### `platoons`

- `platoons_pkey`: CREATE UNIQUE INDEX platoons_pkey ON public.platoons USING btree (platoon_id)

### `player_exclusion_audit`

- `player_exclusion_audit_pkey`: CREATE UNIQUE INDEX player_exclusion_audit_pkey ON public.player_exclusion_audit USING btree (audit_id)

### `player_exclusions`

- `ix_player_exclusions_active`: CREATE INDEX ix_player_exclusions_active ON public.player_exclusions USING btree (platform, persona_id) WHERE active
- `player_exclusions_pkey`: CREATE UNIQUE INDEX player_exclusions_pkey ON public.player_exclusions USING btree (platform, persona_id)

### `profile_soldiers`

- `profile_soldiers_pkey`: CREATE UNIQUE INDEX profile_soldiers_pkey ON public.profile_soldiers USING btree (profile_id, soldier_id)

### `request_gates`

- `request_gates_pkey`: CREATE UNIQUE INDEX request_gates_pkey ON public.request_gates USING btree (egress_key)

### `runtime_budgets`

- `runtime_budgets_pkey`: CREATE UNIQUE INDEX runtime_budgets_pkey ON public.runtime_budgets USING btree (singleton)

### `soak_round_jobs`

- `ix_soak_round_jobs_round`: CREATE INDEX ix_soak_round_jobs_round ON public.soak_round_jobs USING btree (run_id, round_number)
- `soak_round_jobs_pkey`: CREATE UNIQUE INDEX soak_round_jobs_pkey ON public.soak_round_jobs USING btree (run_id, round_number, soldier_id)
- `uq_soak_round_job_id`: CREATE UNIQUE INDEX uq_soak_round_job_id ON public.soak_round_jobs USING btree (job_id)

### `soak_rounds`

- `soak_rounds_pkey`: CREATE UNIQUE INDEX soak_rounds_pkey ON public.soak_rounds USING btree (run_id, round_number)

### `soak_runs`

- `soak_runs_pkey`: CREATE UNIQUE INDEX soak_runs_pkey ON public.soak_runs USING btree (run_id)

### `soldier_names`

- `ix_soldier_names_name_lower`: CREATE INDEX ix_soldier_names_name_lower ON public.soldier_names USING btree (lower(name))
- `soldier_names_pkey`: CREATE UNIQUE INDEX soldier_names_pkey ON public.soldier_names USING btree (soldier_name_id)
- `uq_soldier_names_soldier_name`: CREATE UNIQUE INDEX uq_soldier_names_soldier_name ON public.soldier_names USING btree (soldier_id, name)

### `soldier_sources`

- `soldier_sources_pkey`: CREATE UNIQUE INDEX soldier_sources_pkey ON public.soldier_sources USING btree (soldier_id, source_type)

### `soldier_vehicle_stats`

- `soldier_vehicle_stats_pkey`: CREATE UNIQUE INDEX soldier_vehicle_stats_pkey ON public.soldier_vehicle_stats USING btree (soldier_id, vehicle_id)

### `soldier_weapon_stats`

- `ix_soldier_weapon_stats_weapon_kills`: CREATE INDEX ix_soldier_weapon_stats_weapon_kills ON public.soldier_weapon_stats USING btree (weapon_id, kills DESC, soldier_id)
- `soldier_weapon_stats_pkey`: CREATE UNIQUE INDEX soldier_weapon_stats_pkey ON public.soldier_weapon_stats USING btree (soldier_id, weapon_id)

### `soldiers`

- `ix_soldiers_current_name_lower`: CREATE INDEX ix_soldiers_current_name_lower ON public.soldiers USING btree (lower(current_name))
- `ix_soldiers_last_seen`: CREATE INDEX ix_soldiers_last_seen ON public.soldiers USING btree (last_seen_at)
- `soldiers_pkey`: CREATE UNIQUE INDEX soldiers_pkey ON public.soldiers USING btree (soldier_id)
- `uq_soldiers_persona_platform`: CREATE UNIQUE INDEX uq_soldiers_persona_platform ON public.soldiers USING btree (persona_id, platform)

### `stage9c_supervision_runs`

- `stage9c_supervision_runs_pkey`: CREATE UNIQUE INDEX stage9c_supervision_runs_pkey ON public.stage9c_supervision_runs USING btree (run_id)
- `uq_stage9c_one_active_run`: CREATE UNIQUE INDEX uq_stage9c_one_active_run ON public.stage9c_supervision_runs USING btree (state) WHERE (state = 'active'::text)

### `vehicle_catalog`

- `vehicle_catalog_pkey`: CREATE UNIQUE INDEX vehicle_catalog_pkey ON public.vehicle_catalog USING btree (vehicle_id)
- `vehicle_catalog_vehicle_guid_key`: CREATE UNIQUE INDEX vehicle_catalog_vehicle_guid_key ON public.vehicle_catalog USING btree (vehicle_guid)

### `vehicle_leaderboard_metrics`

- `ix_vehicle_leaderboard_metrics_kills_top`: CREATE INDEX ix_vehicle_leaderboard_metrics_kills_top ON public.vehicle_leaderboard_metrics USING btree (vehicle_id, kills DESC NULLS LAST, soldier_id)
- `ix_vehicle_leaderboard_metrics_kpm_top`: CREATE INDEX ix_vehicle_leaderboard_metrics_kpm_top ON public.vehicle_leaderboard_metrics USING btree (vehicle_id, kpm DESC NULLS LAST, soldier_id)
- `vehicle_leaderboard_metrics_pkey`: CREATE UNIQUE INDEX vehicle_leaderboard_metrics_pkey ON public.vehicle_leaderboard_metrics USING btree (soldier_id, vehicle_id)

### `weapon_catalog`

- `weapon_catalog_pkey`: CREATE UNIQUE INDEX weapon_catalog_pkey ON public.weapon_catalog USING btree (weapon_id)
- `weapon_catalog_weapon_guid_key`: CREATE UNIQUE INDEX weapon_catalog_weapon_guid_key ON public.weapon_catalog USING btree (weapon_guid)

### `weapon_leaderboard_metrics`

- `ix_weapon_leaderboard_metrics_accuracy_top`: CREATE INDEX ix_weapon_leaderboard_metrics_accuracy_top ON public.weapon_leaderboard_metrics USING btree (weapon_id, accuracy DESC NULLS LAST, soldier_id)
- `ix_weapon_leaderboard_metrics_kills_top`: CREATE INDEX ix_weapon_leaderboard_metrics_kills_top ON public.weapon_leaderboard_metrics USING btree (weapon_id, kills DESC NULLS LAST, soldier_id)
- `ix_weapon_leaderboard_metrics_kpm_top`: CREATE INDEX ix_weapon_leaderboard_metrics_kpm_top ON public.weapon_leaderboard_metrics USING btree (weapon_id, kpm DESC NULLS LAST, soldier_id)
- `weapon_leaderboard_metrics_pkey`: CREATE UNIQUE INDEX weapon_leaderboard_metrics_pkey ON public.weapon_leaderboard_metrics USING btree (soldier_id, weapon_id)

## Constraints (183)


### `alembic_version`

- `alembic_version_pkc`: p|PRIMARY KEY (version_num)

### `battlelog_profiles`

- `battlelog_profiles_access_state_check`: c|CHECK ((access_state = ANY (ARRAY['public_country'::text, 'public_no_country'::text, 'friends_only'::text, 'not_found'::text, 'error'::text])))
- `battlelog_profiles_country_upper_check`: c|CHECK (((country_code IS NULL) OR ((country_code)::text = upper((country_code)::text))))
- `battlelog_profiles_pkey`: p|PRIMARY KEY (profile_id)

### `collection_events`

- `collection_events_attempt_check`: c|CHECK (((attempt_number IS NULL) OR (attempt_number >= 0)))
- `collection_events_collector_uuid_fkey`: f|FOREIGN KEY (collector_uuid) REFERENCES collectors(collector_uuid) ON DELETE SET NULL
- `collection_events_duration_check`: c|CHECK (((duration_ms IS NULL) OR (duration_ms >= 0)))
- `collection_events_event_type_nonempty`: c|CHECK ((btrim(event_type) <> ''::text))
- `collection_events_http_status_check`: c|CHECK (((http_status IS NULL) OR ((http_status >= 100) AND (http_status <= 599))))
- `collection_events_lane_check`: c|CHECK (((lane IS NULL) OR (lane = ANY (ARRAY['background'::text, 'interactive'::text]))))
- `collection_events_pkey`: p|PRIMARY KEY (event_id)
- `collection_events_platform_check`: c|CHECK (((platform IS NULL) OR (platform = ANY (ARRAY['pc'::text, 'ps4'::text, 'xboxone'::text]))))
- `collection_events_resource_check`: c|CHECK (((resource IS NULL) OR (resource = ANY (ARRAY['detailed'::text, 'profile'::text, 'weapons'::text, 'vehicles'::text]))))
- `collection_events_soldier_id_fkey`: f|FOREIGN KEY (soldier_id) REFERENCES soldiers(soldier_id) ON DELETE SET NULL

### `collection_jobs`

- `collection_jobs_attempt_count_check`: c|CHECK ((attempt_count >= 0))
- `collection_jobs_collector_uuid_fkey`: f|FOREIGN KEY (collector_uuid) REFERENCES collectors(collector_uuid) ON DELETE SET NULL
- `collection_jobs_lane_check`: c|CHECK ((lane = ANY (ARRAY['background'::text, 'interactive'::text])))
- `collection_jobs_lease_shape_check`: c|CHECK ((((status = 'pending'::text) AND (collector_uuid IS NULL) AND (lease_token IS NULL) AND (claimed_at IS NULL) AND (started_at IS NULL) AND (lease_expires_at IS NULL)) OR ((status = 'claimed'::text) AND (collector_uuid IS NOT NULL) AND (lease_token IS NOT NULL) AND (claimed_at IS NOT NULL) AND (started_at IS NULL) AND (lease_expires_at IS NOT NULL)) OR ((status = 'running'::text) AND (collector_uuid IS NOT NULL) AND (lease_token IS NOT NULL) AND (claimed_at IS NOT NULL) AND (started_at IS NOT NULL) AND (lease_expires_at IS NOT NULL))))
- `collection_jobs_pkey`: p|PRIMARY KEY (job_id)
- `collection_jobs_priority_class_check`: c|CHECK ((priority_class = ANY (ARRAY['interactive'::text, 'active'::text, 'recent'::text, 'bootstrap'::text])))
- `collection_jobs_resource_check`: c|CHECK ((resource = ANY (ARRAY['detailed'::text, 'profile'::text, 'weapons'::text, 'vehicles'::text])))
- `collection_jobs_soldier_id_fkey`: f|FOREIGN KEY (soldier_id) REFERENCES soldiers(soldier_id) ON DELETE CASCADE
- `collection_jobs_status_check`: c|CHECK ((status = ANY (ARRAY['pending'::text, 'claimed'::text, 'running'::text])))
- `uq_collection_jobs_soldier_resource`: u|UNIQUE (soldier_id, resource)

### `collection_state`

- `collection_state_detailed_failures_check`: c|CHECK ((detailed_consecutive_failures >= 0))
- `collection_state_detailed_state_check`: c|CHECK ((detailed_state = ANY (ARRAY['never_attempted'::text, 'success'::text, 'temporary_failure'::text, 'unavailable'::text])))
- `collection_state_pkey`: p|PRIMARY KEY (soldier_id)
- `collection_state_profile_failures_check`: c|CHECK ((profile_consecutive_failures >= 0))
- `collection_state_profile_state_check`: c|CHECK ((profile_state = ANY (ARRAY['never_attempted'::text, 'success'::text, 'temporary_failure'::text, 'unavailable'::text])))
- `collection_state_soldier_id_fkey`: f|FOREIGN KEY (soldier_id) REFERENCES soldiers(soldier_id) ON DELETE CASCADE
- `collection_state_vehicles_failures_check`: c|CHECK ((vehicles_consecutive_failures >= 0))
- `collection_state_vehicles_state_check`: c|CHECK ((vehicles_state = ANY (ARRAY['never_attempted'::text, 'success'::text, 'temporary_failure'::text, 'unavailable'::text])))
- `collection_state_weapons_failures_check`: c|CHECK ((weapons_consecutive_failures >= 0))
- `collection_state_weapons_state_check`: c|CHECK ((weapons_state = ANY (ARRAY['never_attempted'::text, 'success'::text, 'temporary_failure'::text, 'unavailable'::text])))

### `collectors`

- `collectors_egress_nonempty`: c|CHECK ((btrim(egress_key) <> ''::text))
- `collectors_heartbeat_state_check`: c|CHECK ((heartbeat_state = ANY (ARRAY['unknown'::text, 'healthy'::text, 'lost'::text])))
- `collectors_hostname_nonempty`: c|CHECK ((btrim(hostname) <> ''::text))
- `collectors_lane_check`: c|CHECK ((lane = ANY (ARRAY['background'::text, 'interactive'::text])))
- `collectors_name_nonempty`: c|CHECK ((btrim(collector_name) <> ''::text))
- `collectors_pkey`: p|PRIMARY KEY (collector_uuid)
- `fk_collectors_current_job`: f|FOREIGN KEY (current_job_id) REFERENCES collection_jobs(job_id) ON DELETE SET NULL

### `detailed_stats_current`

- `detailed_stats_current_pkey`: p|PRIMARY KEY (soldier_id)
- `detailed_stats_current_soldier_id_fkey`: f|FOREIGN KEY (soldier_id) REFERENCES soldiers(soldier_id) ON DELETE CASCADE

### `detailed_stats_history`

- `detailed_stats_history_pkey`: p|PRIMARY KEY (snapshot_id)
- `detailed_stats_history_soldier_id_fkey`: f|FOREIGN KEY (soldier_id) REFERENCES soldiers(soldier_id) ON DELETE CASCADE

### `discovery_state`

- `discovery_state_alias_id_check`: c|CHECK ((last_alias_id >= 0))
- `discovery_state_pkey`: p|PRIMARY KEY (source_name)

### `equipment_population`

- `equipment_population_kind`: c|CHECK ((kind = ANY (ARRAY['weapon'::text, 'vehicle'::text])))
- `equipment_population_nonnegative`: c|CHECK ((population >= 0))
- `equipment_population_pkey`: p|PRIMARY KEY (kind, item_id, platform)
- `equipment_population_platform`: c|CHECK ((platform = ANY (ARRAY['pc'::text, 'ps4'::text, 'xboxone'::text])))

### `equipment_rank_generations`

- `ck_rank_generation_snapshot_format`: c|CHECK ((snapshot_format = ANY (ARRAY[0, 1])))
- `equipment_rank_generation_count`: c|CHECK (((row_count IS NULL) OR (row_count >= 0)))
- `equipment_rank_generation_input_version`: c|CHECK (((input_scope_version IS NULL) OR (input_scope_version >= 0)))
- `equipment_rank_generation_kind`: c|CHECK ((kind = ANY (ARRAY['weapon'::text, 'vehicle'::text])))
- `equipment_rank_generation_metric`: c|CHECK ((((kind = 'weapon'::text) AND (metric = ANY (ARRAY['kills'::text, 'kpm'::text, 'accuracy'::text]))) OR ((kind = 'vehicle'::text) AND (metric = ANY (ARRAY['kills'::text, 'kpm'::text])))))
- `equipment_rank_generation_platform`: c|CHECK ((platform = ANY (ARRAY['pc'::text, 'ps4'::text, 'xboxone'::text, 'all'::text])))
- `equipment_rank_generation_status`: c|CHECK ((status = ANY (ARRAY['building'::text, 'validated'::text, 'published'::text, 'retired'::text, 'failed'::text])))
- `equipment_rank_generations_pkey`: p|PRIMARY KEY (generation_id)

### `equipment_rank_published`

- `equipment_rank_published_generation_id_fkey`: f|FOREIGN KEY (generation_id) REFERENCES equipment_rank_generations(generation_id)
- `equipment_rank_published_kind`: c|CHECK ((kind = ANY (ARRAY['weapon'::text, 'vehicle'::text])))
- `equipment_rank_published_pkey`: p|PRIMARY KEY (kind, item_id, platform, metric)
- `equipment_rank_published_platform`: c|CHECK ((platform = ANY (ARRAY['pc'::text, 'ps4'::text, 'xboxone'::text, 'all'::text])))

### `equipment_rank_rows`

- `equipment_rank_positive`: c|CHECK (((rank >= 1) AND ("position" >= 1)))
- `equipment_rank_rows_generation_id_fkey`: f|FOREIGN KEY (generation_id) REFERENCES equipment_rank_generations(generation_id) ON DELETE CASCADE
- `equipment_rank_rows_pkey`: p|PRIMARY KEY (generation_id, soldier_id)
- `uq_equipment_rank_generation_position`: u|UNIQUE (generation_id, "position")

### `equipment_rank_scope_versions`

- `equipment_rank_scope_kind`: c|CHECK ((kind = ANY (ARRAY['weapon'::text, 'vehicle'::text])))
- `equipment_rank_scope_platform`: c|CHECK ((platform = ANY (ARRAY['pc'::text, 'ps4'::text, 'xboxone'::text, 'all'::text])))
- `equipment_rank_scope_version_nonnegative`: c|CHECK ((version >= 0))
- `equipment_rank_scope_versions_pkey`: p|PRIMARY KEY (kind, item_id, platform)

### `manual_collection_requests`

- `manual_collection_requests_pkey`: p|PRIMARY KEY (request_id)
- `manual_collection_requests_soldier_id_fkey`: f|FOREIGN KEY (soldier_id) REFERENCES soldiers(soldier_id) ON DELETE RESTRICT
- `manual_requests_kind_check`: c|CHECK ((request_kind = ANY (ARRAY['add'::text, 'refresh'::text])))
- `manual_requests_status_check`: c|CHECK ((status = ANY (ARRAY['accepted'::text, 'queued'::text, 'collecting'::text, 'completed'::text, 'retrying'::text, 'rejected'::text])))
- `manual_requests_time_check`: c|CHECK (((completed_at IS NULL) OR (completed_at >= requested_at)))

### `manual_request_cooldowns`

- `manual_request_cooldowns_last_request_id_fkey`: f|FOREIGN KEY (last_request_id) REFERENCES manual_collection_requests(request_id) ON DELETE RESTRICT
- `manual_request_cooldowns_pkey`: p|PRIMARY KEY (soldier_id)
- `manual_request_cooldowns_soldier_id_fkey`: f|FOREIGN KEY (soldier_id) REFERENCES soldiers(soldier_id) ON DELETE CASCADE

### `manual_soldier_verifications`

- `manual_soldier_verifications_pkey`: p|PRIMARY KEY (verification_id)
- `manual_soldier_verifications_soldier_id_fkey`: f|FOREIGN KEY (soldier_id) REFERENCES soldiers(soldier_id)
- `manual_verify_attempt_count_check`: c|CHECK ((attempt_count >= 0))
- `manual_verify_persona_positive`: c|CHECK ((persona_id > 0))
- `manual_verify_platform_check`: c|CHECK ((platform = ANY (ARRAY['pc'::text, 'ps4'::text, 'xboxone'::text])))
- `manual_verify_status_check`: c|CHECK ((status = ANY (ARRAY['pending'::text, 'claimed'::text, 'verified'::text, 'rejected'::text])))
- `uq_manual_verify_identity`: u|UNIQUE (persona_id, platform)

### `outbound_dispatches`

- `outbound_dispatch_ack_after_send`: c|CHECK (((acknowledged_at IS NULL) OR (acknowledged_at >= send_marked_at)))
- `outbound_dispatch_attempt_positive`: c|CHECK (((job_id > 0) AND (attempt_number > 0)))
- `outbound_dispatch_lane`: c|CHECK ((lane = ANY (ARRAY['background'::text, 'interactive'::text])))
- `outbound_dispatch_nonempty`: c|CHECK (((btrim(egress_key) <> ''::text) AND (btrim(payload_fingerprint) <> ''::text)))
- `outbound_dispatch_phase`: c|CHECK ((phase = ANY (ARRAY['admitted'::text, 'may_have_sent'::text, 'acknowledged'::text, 'ambiguous'::text])))
- `outbound_dispatch_phase_timestamps`: c|CHECK ((((phase = 'admitted'::text) AND (send_marked_at IS NULL) AND (acknowledged_at IS NULL)) OR ((phase = ANY (ARRAY['may_have_sent'::text, 'ambiguous'::text])) AND (send_marked_at IS NOT NULL) AND (acknowledged_at IS NULL)) OR ((phase = 'acknowledged'::text) AND (send_marked_at IS NOT NULL) AND (acknowledged_at IS NOT NULL))))
- `outbound_dispatch_request_ordinal_positive`: c|CHECK ((request_ordinal > 0))
- `outbound_dispatch_resource`: c|CHECK ((resource = ANY (ARRAY['detailed'::text, 'profile'::text, 'weapons'::text, 'vehicles'::text])))
- `outbound_dispatch_send_after_admit`: c|CHECK (((send_marked_at IS NULL) OR (send_marked_at >= admitted_at)))
- `outbound_dispatches_pkey`: p|PRIMARY KEY (dispatch_id)
- `uq_outbound_dispatch_physical_identity`: u|UNIQUE (job_id, attempt_number, resource, lease_token, request_ordinal)

### `platoon_requests`

- `platoon_requests_pkey`: p|PRIMARY KEY (platoon_id)
- `platoon_requests_platoon_id_check`: c|CHECK ((platoon_id > 0))
- `platoon_requests_status_check`: c|CHECK ((status = ANY (ARRAY['pending'::text, 'running'::text, 'complete'::text, 'failed'::text])))

### `platoon_roster_accounts`

- `platoon_roster_accounts_battlelog_account_id_check`: c|CHECK ((battlelog_account_id > 0))
- `platoon_roster_accounts_pkey`: p|PRIMARY KEY (platoon_id, battlelog_account_id)
- `platoon_roster_accounts_platoon_id_fkey`: f|FOREIGN KEY (platoon_id) REFERENCES platoons(platoon_id) ON DELETE CASCADE
- `platoon_roster_accounts_role_check`: c|CHECK ((role = ANY (ARRAY['founder'::text, 'leader'::text, 'member'::text])))

### `platoon_roster_personas`

- `platoon_roster_personas_battlelog_platform_code_check`: c|CHECK ((battlelog_platform_code = ANY (ARRAY[1, 2, 4, 32, 64])))
- `platoon_roster_personas_persona_id_check`: c|CHECK ((persona_id > 0))
- `platoon_roster_personas_pkey`: p|PRIMARY KEY (platoon_id, battlelog_account_id, battlelog_platform_code, persona_id)
- `platoon_roster_personas_platform_family_check`: c|CHECK ((platform_family = ANY (ARRAY['pc'::text, 'xbox'::text, 'playstation'::text])))
- `platoon_roster_personas_platoon_id_battlelog_account_id_fkey`: f|FOREIGN KEY (platoon_id, battlelog_account_id) REFERENCES platoon_roster_accounts(platoon_id, battlelog_account_id) ON DELETE CASCADE

### `platoon_soldier_discovery`

- `platoon_soldier_discovery_pkey`: p|PRIMARY KEY (soldier_id)
- `platoon_soldier_discovery_soldier_id_fkey`: f|FOREIGN KEY (soldier_id) REFERENCES soldiers(soldier_id)
- `platoon_soldier_discovery_status_check`: c|CHECK ((status = ANY (ARRAY['pending'::text, 'running'::text, 'complete'::text, 'failed'::text])))

### `platoon_sync_runs`

- `platoon_sync_runs_pkey`: p|PRIMARY KEY (sync_id)
- `platoon_sync_runs_platoon_id_fkey`: f|FOREIGN KEY (platoon_id) REFERENCES platoons(platoon_id) ON DELETE CASCADE

### `platoon_work_leases`

- `platoon_work_leases_pkey`: p|PRIMARY KEY (platoon_id)
- `platoon_work_leases_work_kind_check`: c|CHECK ((work_kind = ANY (ARRAY['request'::text, 'refresh'::text])))

### `platoons`

- `platoons_official_member_count_check`: c|CHECK ((official_member_count >= 0))
- `platoons_pkey`: p|PRIMARY KEY (platoon_id)
- `platoons_platoon_id_check`: c|CHECK ((platoon_id > 0))

### `player_exclusion_audit`

- `player_exclusion_audit_action_check`: c|CHECK ((action = ANY (ARRAY['exclude'::text, 'restore'::text, 'purge'::text, 'note'::text])))
- `player_exclusion_audit_pkey`: p|PRIMARY KEY (audit_id)

### `player_exclusions`

- `player_exclusions_persona_id_check`: c|CHECK ((persona_id > 0))
- `player_exclusions_pkey`: p|PRIMARY KEY (platform, persona_id)
- `player_exclusions_platform_check`: c|CHECK ((platform = ANY (ARRAY['pc'::text, 'ps4'::text, 'xboxone'::text])))

### `profile_soldiers`

- `profile_soldiers_pkey`: p|PRIMARY KEY (profile_id, soldier_id)
- `profile_soldiers_profile_id_fkey`: f|FOREIGN KEY (profile_id) REFERENCES battlelog_profiles(profile_id) ON DELETE CASCADE
- `profile_soldiers_soldier_id_fkey`: f|FOREIGN KEY (soldier_id) REFERENCES soldiers(soldier_id) ON DELETE CASCADE

### `request_gates`

- `request_gates_egress_nonempty`: c|CHECK ((btrim(egress_key) <> ''::text))
- `request_gates_pkey`: p|PRIMARY KEY (egress_key)

### `runtime_budgets`

- `runtime_budgets_background_range`: c|CHECK (((background_slots_per_hour >= 1) AND (background_slots_per_hour <= physical_dispatches_per_hour)))
- `runtime_budgets_physical_range`: c|CHECK (((physical_dispatches_per_hour >= 1) AND (physical_dispatches_per_hour <= 5760)))
- `runtime_budgets_pkey`: p|PRIMARY KEY (singleton)
- `runtime_budgets_singleton`: c|CHECK ((singleton = true))

### `soak_round_jobs`

- `soak_job_outcome`: c|CHECK ((outcome = ANY (ARRAY['pending'::text, 'success'::text, 'failed'::text, 'abandoned'::text])))
- `soak_job_positive`: c|CHECK ((job_id > 0))
- `soak_round_jobs_pkey`: p|PRIMARY KEY (run_id, round_number, soldier_id)
- `soak_round_jobs_run_id_round_number_fkey`: f|FOREIGN KEY (run_id, round_number) REFERENCES soak_rounds(run_id, round_number) ON DELETE RESTRICT
- `uq_soak_round_job_id`: u|UNIQUE (job_id)

### `soak_rounds`

- `soak_round_number`: c|CHECK (((round_number >= 1) AND (round_number <= 12)))
- `soak_round_state`: c|CHECK ((state = ANY (ARRAY['planned'::text, 'enqueued'::text, 'completed'::text, 'failed'::text])))
- `soak_round_timestamps`: c|CHECK ((((state = 'planned'::text) AND (enqueued_at IS NULL) AND (completed_at IS NULL)) OR ((state = 'enqueued'::text) AND (enqueued_at IS NOT NULL) AND (completed_at IS NULL)) OR ((state = ANY (ARRAY['completed'::text, 'failed'::text])) AND (enqueued_at IS NOT NULL))))
- `soak_rounds_pkey`: p|PRIMARY KEY (run_id, round_number)
- `soak_rounds_run_id_fkey`: f|FOREIGN KEY (run_id) REFERENCES soak_runs(run_id) ON DELETE RESTRICT

### `soak_runs`

- `soak_run_bounds`: c|CHECK (((baseline_event_id >= 0) AND (attempt_ceiling > 0) AND (site_attempt_ceiling > 0)))
- `soak_run_state`: c|CHECK ((state = ANY (ARRAY['prepared'::text, 'running'::text, 'stopping'::text, 'completed'::text, 'failed'::text, 'stopped'::text])))
- `soak_run_times`: c|CHECK ((((start_at IS NULL) AND (deadline_at IS NULL)) OR ((start_at IS NOT NULL) AND (deadline_at > start_at))))
- `soak_runs_pkey`: p|PRIMARY KEY (run_id)

### `soldier_names`

- `soldier_names_name_nonempty`: c|CHECK ((btrim(name) <> ''::text))
- `soldier_names_pkey`: p|PRIMARY KEY (soldier_name_id)
- `soldier_names_soldier_id_fkey`: f|FOREIGN KEY (soldier_id) REFERENCES soldiers(soldier_id) ON DELETE CASCADE
- `uq_soldier_names_soldier_name`: u|UNIQUE (soldier_id, name)

### `soldier_sources`

- `soldier_sources_pkey`: p|PRIMARY KEY (soldier_id, source_type)
- `soldier_sources_soldier_id_fkey`: f|FOREIGN KEY (soldier_id) REFERENCES soldiers(soldier_id) ON DELETE CASCADE
- `soldier_sources_type_check`: c|CHECK ((source_type = ANY (ARRAY['bf4sw'::text, 'manual'::text])))

### `soldier_vehicle_stats`

- `soldier_vehicle_stats_pkey`: p|PRIMARY KEY (soldier_id, vehicle_id)
- `soldier_vehicle_stats_soldier_id_fkey`: f|FOREIGN KEY (soldier_id) REFERENCES soldiers(soldier_id) ON DELETE CASCADE
- `soldier_vehicle_stats_vehicle_id_fkey`: f|FOREIGN KEY (vehicle_id) REFERENCES vehicle_catalog(vehicle_id) ON DELETE CASCADE

### `soldier_weapon_stats`

- `soldier_weapon_stats_pkey`: p|PRIMARY KEY (soldier_id, weapon_id)
- `soldier_weapon_stats_soldier_id_fkey`: f|FOREIGN KEY (soldier_id) REFERENCES soldiers(soldier_id) ON DELETE CASCADE
- `soldier_weapon_stats_weapon_id_fkey`: f|FOREIGN KEY (weapon_id) REFERENCES weapon_catalog(weapon_id) ON DELETE CASCADE

### `soldiers`

- `soldiers_name_nonempty`: c|CHECK ((btrim(current_name) <> ''::text))
- `soldiers_pkey`: p|PRIMARY KEY (soldier_id)
- `soldiers_platform_check`: c|CHECK ((platform = ANY (ARRAY['pc'::text, 'ps4'::text, 'xboxone'::text])))
- `uq_soldiers_persona_platform`: u|UNIQUE (persona_id, platform)

### `stage9c_supervision_runs`

- `stage9c_run_abort_pair`: c|CHECK ((((abort_at IS NULL) AND (abort_reason IS NULL)) OR ((abort_at IS NOT NULL) AND (abort_reason IS NOT NULL) AND (btrim(abort_reason) <> ''::text))))
- `stage9c_run_aborted_reason`: c|CHECK (((state <> 'aborted'::text) OR (abort_at IS NOT NULL)))
- `stage9c_run_activation_dates`: c|CHECK (((state = 'prepared'::text) OR ((started_at IS NOT NULL) AND (deadline_at IS NOT NULL))))
- `stage9c_run_active_lease`: c|CHECK (((state <> 'active'::text) OR ((watchdog_owner IS NOT NULL) AND (heartbeat_at IS NOT NULL) AND (lease_expires_at IS NOT NULL) AND (lease_expires_at > heartbeat_at))))
- `stage9c_run_boundary`: c|CHECK ((since_event_id >= 0))
- `stage9c_run_generation`: c|CHECK ((watchdog_generation >= 0))
- `stage9c_run_six_hour_deadline`: c|CHECK ((((started_at IS NULL) AND (deadline_at IS NULL)) OR ((started_at IS NOT NULL) AND (deadline_at = (started_at + '06:00:00'::interval)))))
- `stage9c_run_state`: c|CHECK ((state = ANY (ARRAY['prepared'::text, 'active'::text, 'aborted'::text, 'completed'::text])))
- `stage9c_supervision_runs_pkey`: p|PRIMARY KEY (run_id)

### `vehicle_catalog`

- `vehicle_catalog_pkey`: p|PRIMARY KEY (vehicle_id)
- `vehicle_catalog_vehicle_guid_key`: u|UNIQUE (vehicle_guid)

### `vehicle_leaderboard_metrics`

- `vehicle_leaderboard_metrics_pkey`: p|PRIMARY KEY (soldier_id, vehicle_id)
- `vehicle_leaderboard_metrics_soldier_id_fkey`: f|FOREIGN KEY (soldier_id) REFERENCES soldiers(soldier_id) ON DELETE CASCADE
- `vehicle_leaderboard_metrics_vehicle_id_fkey`: f|FOREIGN KEY (vehicle_id) REFERENCES vehicle_catalog(vehicle_id) ON DELETE CASCADE

### `weapon_catalog`

- `weapon_catalog_pkey`: p|PRIMARY KEY (weapon_id)
- `weapon_catalog_weapon_guid_key`: u|UNIQUE (weapon_guid)

### `weapon_leaderboard_metrics`

- `weapon_leaderboard_metrics_pkey`: p|PRIMARY KEY (soldier_id, weapon_id)
- `weapon_leaderboard_metrics_soldier_id_fkey`: f|FOREIGN KEY (soldier_id) REFERENCES soldiers(soldier_id) ON DELETE CASCADE
- `weapon_leaderboard_metrics_weapon_id_fkey`: f|FOREIGN KEY (weapon_id) REFERENCES weapon_catalog(weapon_id) ON DELETE CASCADE
