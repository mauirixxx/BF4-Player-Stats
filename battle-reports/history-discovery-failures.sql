-- Persistent failed-history cooldowns for manual player-driven discovery.
CREATE TABLE IF NOT EXISTS history_discovery_failures (
    platform smallint NOT NULL,
    persona_id bigint NOT NULL,
    failures integer NOT NULL DEFAULT 0,
    last_failed_at timestamptz NOT NULL DEFAULT now(),
    retry_after timestamptz NOT NULL,
    last_reason text NOT NULL,
    PRIMARY KEY (platform, persona_id)
);
