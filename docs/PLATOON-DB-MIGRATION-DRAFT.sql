-- Draft only. NOT applied to production. Reviewed against 2026-10-17 live schema snapshot.
-- Official Battlelog accounts are roster members; personas are associated evidence.
CREATE TABLE IF NOT EXISTS platoons (
  platoon_id bigint PRIMARY KEY CHECK (platoon_id > 0),
  name text NOT NULL,
  tag text NOT NULL,
  official_member_count integer NOT NULL CHECK (official_member_count >= 0),
  battlelog_created_at timestamptz,
  first_seen_at timestamptz NOT NULL DEFAULT now(),
  last_checked_at timestamptz,
  last_success_at timestamptz,
  last_error text,
  next_refresh_at timestamptz,
  discovery_source text NOT NULL DEFAULT 'manual'
);
CREATE TABLE IF NOT EXISTS platoon_roster_accounts (
  platoon_id bigint NOT NULL REFERENCES platoons(platoon_id) ON DELETE CASCADE,
  battlelog_account_id bigint NOT NULL CHECK (battlelog_account_id > 0),
  account_name text,
  role text NOT NULL CHECK (role IN ('founder','leader','member')),
  joined_at timestamptz,
  first_seen_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  is_current boolean NOT NULL DEFAULT true,
  PRIMARY KEY (platoon_id, battlelog_account_id)
);
CREATE TABLE IF NOT EXISTS platoon_roster_personas (
  platoon_id bigint NOT NULL,
  battlelog_account_id bigint NOT NULL,
  battlelog_platform_code integer NOT NULL CHECK (battlelog_platform_code IN (1,2,4,32,64)),
  persona_id bigint NOT NULL CHECK (persona_id > 0),
  persona_name text NOT NULL,
  platform_family text NOT NULL CHECK (platform_family IN ('pc','xbox','playstation')),
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  is_current boolean NOT NULL DEFAULT true,
  PRIMARY KEY (platoon_id,battlelog_account_id,battlelog_platform_code,persona_id),
  FOREIGN KEY (platoon_id,battlelog_account_id)
    REFERENCES platoon_roster_accounts(platoon_id,battlelog_account_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_platoon_personas_identity ON platoon_roster_personas(platform_family,persona_id) WHERE is_current;
CREATE INDEX IF NOT EXISTS ix_platoon_accounts_account ON platoon_roster_accounts(battlelog_account_id) WHERE is_current;
CREATE TABLE IF NOT EXISTS platoon_sync_runs (
  sync_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  platoon_id bigint NOT NULL REFERENCES platoons(platoon_id) ON DELETE CASCADE,
  started_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz,
  success boolean,
  account_count integer,
  bf4_platform_records integer,
  response_bytes integer,
  error text
);
-- Do not write soldiers, battlelog_profiles, profile_soldiers, or stat tables.
-- Do not promote persona association to confirmed soldier membership.
-- Apply only via reviewed migration, with restricted collector role grants.
