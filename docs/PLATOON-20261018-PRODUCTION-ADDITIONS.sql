-- Additive, idempotent migration for platoon metadata collected from Battlelog.
-- Applied to bf4_playerstats production on 2026-10-18.
-- Safe to reapply. Does not remove historical roster or soldier records.
ALTER TABLE platoons ADD COLUMN IF NOT EXISTS emblem_path text;
ALTER TABLE platoons ADD COLUMN IF NOT EXISTS website_url text;
