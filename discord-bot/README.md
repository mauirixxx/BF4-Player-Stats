# BF4PS Discord bot

**Status: design phase; not deployed.** Entirely new Discord application, independent of BF4 Server Watcher.

- Game statistics: **100% read-only** access to BF4PS production database, including no refresh queue writes.
- Bot coordination: a **separate bot-owned PostgreSQL database** for Discord master lease, node health, guild settings, handoff, and audit events.
- Multi-node high availability modeled on BF4SW's proven `discord_leader.py` and Alembic control-plane migrations, adapted to this bot.
- Discord result/embeds: **awaiting user screenshots**; data contracts can be designed first.

Design documents: [architecture](../docs/DISCORD-BOT-ARCHITECTURE.md) and [control-plane design](../docs/DISCORD-BOT-CONTROL-PLANE-DESIGN.md). Verify live schemas before writing query code or migrations.
