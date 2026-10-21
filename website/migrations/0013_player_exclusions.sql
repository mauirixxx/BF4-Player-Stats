-- BF4PS player exclusion registry, additive migration proposal.
-- Run only after matching this against production Alembic 0012 and with a migration owner.
-- This file is intentionally NOT auto-applied by website startup.
BEGIN;
CREATE TABLE IF NOT EXISTS public.player_exclusions (
    platform text NOT NULL CHECK (platform IN ('pc','ps4','xboxone')),
    persona_id bigint NOT NULL CHECK (persona_id > 0),
    reason_code text NOT NULL,
    private_note text,
    created_by text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    active boolean NOT NULL DEFAULT true,
    PRIMARY KEY (platform, persona_id)
);
CREATE TABLE IF NOT EXISTS public.player_exclusion_audit (
    audit_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    platform text NOT NULL,
    persona_id bigint NOT NULL,
    action text NOT NULL CHECK (action IN ('exclude','restore','purge','note')),
    actor text NOT NULL,
    reason_code text,
    private_note text,
    occurred_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_player_exclusions_active
    ON public.player_exclusions (platform, persona_id) WHERE active;
COMMIT;
