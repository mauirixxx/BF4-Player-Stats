# BF4PS Discord bot

**Status: deployed two-node HA, `/ping`, guild administration, and live `/pstats player` detailed-statistics overview verified by operator (2026-10-22).** Independent Discord application, separate from BF4 Server Watcher.

- Game statistics: **100% read-only** access to BF4PS production database, including no refresh queue writes.
- Bot coordination: a **separate bot-owned PostgreSQL database** for Discord master lease, node health, guild settings, handoff, and audit events.
- Multi-node high availability modeled on BF4SW's proven `discord_leader.py` and Alembic control-plane migrations, adapted to this bot.
- Discord results: native overview embed with rank, time played, kills/deaths, ratios, accuracy, killstreak, class scores, and snapshot freshness. Operator verified `mauirixxx` and `FooeY` in Discord.

Design documents: [architecture](../docs/DISCORD-BOT-ARCHITECTURE.md) and [control-plane design](../docs/DISCORD-BOT-CONTROL-PLANE-DESIGN.md). Verify live schemas before writing query code or migrations.

## Live deployment (2026-10-22)
- RNT-01 and MAK-01 run independent Docker containers using PostgreSQL lease generation fencing; only the leader connects to Discord.
- Bot identity: `BF4 Player Stats#4096`. Slash command `/ping` is globally registered and has been successfully invoked in Discord; response is ephemeral and validates the current leadership generation.
- Docker restart policy: `unless-stopped` on both nodes. Runtime token/DSN stay in private host `.env` files, never in Git.
- For operational evidence, test limitations, and next steps see [HA rollout](../docs/DISCORD-BOT-HA-ROLLOUT.md). Player overview is live; equipment statistics and leaderboards are not yet implemented.
