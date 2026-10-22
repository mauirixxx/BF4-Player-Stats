# Discord statistics database: least-privilege access

As of 2026-10-22, the live `bf4_playerstats` database on `mak-db-02` reports Alembic `0018_distributed_rank_queue`.

A dedicated PostgreSQL role `bf4ps_discord_readonly` was created **NOLOGIN**, with CONNECT on `bf4_playerstats`, USAGE on schema `public`, and SELECT only on these tables: `soldiers`, `soldier_names`, `detailed_stats_current`, `soldier_weapon_stats`, `soldier_vehicle_stats`, `weapon_catalog`, `vehicle_catalog`, `weapon_leaderboard_metrics`, `vehicle_leaderboard_metrics`, `equipment_population`, `equipment_rank_published`, `equipment_rank_rows`.

The role has no write privileges, no privileges on `player_exclusions`, no superuser/create role/create database privileges, and no default privileges for future tables. Tests confirmed SELECT on soldiers, no INSERT on soldiers, and no SELECT on player_exclusions.

## Credential activation (operator action)

On `mak-db-02`, run `runuser -u postgres -- psql -d bf4_playerstats` then use `\password bf4ps_discord_readonly` interactively (do not put secrets in shell history or chat). Once the password is set, run `ALTER ROLE bf4ps_discord_readonly LOGIN;` and exit with `\q`.

On both `mak-01` and `rnt-01`, edit `/opt/bf4ps-discord/discord-bot/.env` and uncomment `BF4PS_STATS_DSN`, replacing the placeholder password with the new password (URL-encode any reserved URL characters). Keep mode 0600. This is separate from the existing Discord HA control-plane DSN. Containers must be recreated to load changed environment variables; a restart alone does not reload an env-file.

**Status:** Role/grants and commented `.env` templates prepared; password not set, role login disabled, no runtime database integration or connectivity verification yet. Verify pg_hba/network/TLS and read-only connection from both nodes before `/pstats` implementation. Do not expose private moderation data.

## Verified live connectivity (2026-10-22)

PostgreSQL `pg_hba.conf` on `mak-db-02` now allows `hostssl bf4_playerstats bf4ps_discord_readonly` from **192.168.10.70/32 (mak-01)** and **192.168.200.47/32 (rnt-01)** using `scram-sha-256`. A timestamped backup was made before the edit; `pg_reload_conf()` returned true. No database restart was required.

Both nodes successfully authenticated with their own local `.env` credentials over TLS and queried the catalog: MAK-01 counted 174 weapons; RNT-01 counted 82 vehicles. Both reported no write access to `soldiers` and no SELECT access to `player_exclusions`. The existing Discord bot containers were not restarted and the statistics DSN has not yet been wired into application code. The initial `NOLOGIN` role has been activated by the operator.

Next: implement the schema-verified read-only query layer, add a separate connection pool and timeouts, and test an HA failover with statistics queries. Use `sslmode=verify-full` and an appropriate CA if available rather than relying solely on `sslmode=require`.
