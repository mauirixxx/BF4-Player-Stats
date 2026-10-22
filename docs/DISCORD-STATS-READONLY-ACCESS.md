# Discord statistics database: least-privilege access

As of 2026-10-22, the live `bf4_playerstats` database on `mak-db-02` reports Alembic `0018_distributed_rank_queue`.

A dedicated PostgreSQL role `bf4ps_discord_readonly` was created **NOLOGIN**, with CONNECT on `bf4_playerstats`, USAGE on schema `public`, and SELECT only on these tables: `soldiers`, `soldier_names`, `detailed_stats_current`, `soldier_weapon_stats`, `soldier_vehicle_stats`, `weapon_catalog`, `vehicle_catalog`, `weapon_leaderboard_metrics`, `vehicle_leaderboard_metrics`, `equipment_population`, `equipment_rank_published`, `equipment_rank_rows`.

The role has no write privileges, no privileges on `player_exclusions`, no superuser/create role/create database privileges, and no default privileges for future tables. Tests confirmed SELECT on soldiers, no INSERT on soldiers, and no SELECT on player_exclusions.

## Credential activation (operator action)

On `mak-db-02`, run `runuser -u postgres -- psql -d bf4_playerstats` then use `\password bf4ps_discord_readonly` interactively (do not put secrets in shell history or chat). Once the password is set, run `ALTER ROLE bf4ps_discord_readonly LOGIN;` and exit with `\q`.

On both `mak-01` and `rnt-01`, edit `/opt/bf4ps-discord/discord-bot/.env` and uncomment `BF4PS_STATS_DSN`, replacing the placeholder password with the new password (URL-encode any reserved URL characters). Keep mode 0600. This is separate from the existing Discord HA control-plane DSN. Containers must be recreated to load changed environment variables; a restart alone does not reload an env-file.

**Status:** Role/grants and commented `.env` templates prepared; password not set, role login disabled, no runtime database integration or connectivity verification yet. Verify pg_hba/network/TLS and read-only connection from both nodes before `/pstats` implementation. Do not expose private moderation data.
