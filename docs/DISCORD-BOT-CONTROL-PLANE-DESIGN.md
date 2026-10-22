# BF4PS Discord Bot — Dedicated Control Plane (approved direction)
Status: implemented control-plane baseline and live two-node HA (2026-10-22). Historical design proposals and untested gates remain below. Independent Discord application and separate PostgreSQL database.

## Non-negotiable database separation
1. **BF4PS statistics database `bf4_playerstats`:** the Discord application has a dedicated read-only credential. No INSERT, UPDATE, DELETE, DDL, refresh enqueueing, or Battlelog collection. Any exclusion-aware read views/functions must be audited and schema-verified.
2. **Bot operations database (proposed `bf4ps_discord`):** independently versioned Alembic migrations; read/write only for bot coordination, guild preferences, operational events, and bot-owned state. Do not replicate game-statistics tables into it.
3. Both may use the existing HA PostgreSQL infrastructure initially, but they are separate logical databases, separate roles, and separate connection pools. Use the primary's failover DNS for control-plane writes; never assume a particular physical DB host is primary.

## BF4SW code we inspected
BF4SW `discord_leader.py` implements `DiscordLeadershipSupervisor` with a DB-backed `discord:leader` lease, 30-second default TTL, 10-second renewal, monotonic local authority deadline measured from *start* of DB request, bounded DB operation timeout, standby polling, and explicit Discord connect/disconnect callbacks. Migration `0011_v3_0_0_discord_leadership.py` adds worker capability records, handoff requests, operator events, and runtime settings. These are reference implementations, not code to copy unreviewed.

## Proposed bot-owned tables
- `bot_nodes`: stable node ID, site, enabled, draining, priority, software version, heartbeat, last error.
- `bot_node_capabilities`: node ID, Discord token/config availability, role eligibility, checked time.
- `bot_leases`: unique lease key, owner node, monotonically increasing generation/fencing token, expires-at, acquired/renewed times.
- `bot_handoff_requests`: target node, expected generation, requester, state, expiry, outcome.
- `bot_runtime_settings`: validated typed settings with scope and audit metadata.
- `discord_guilds`: Discord snowflake guild ID, installation/last-seen timestamps, enabled state.
- `discord_guild_settings`: guild ID, scoped configuration, changed-by and changed-at.
- `bot_operator_events`: deduplicated incidents, first/last occurrence, resolution and notification state.
- `bot_command_metrics`: bounded/aggregated command timings and failures; define retention before implementation.
Tables and constraints are proposals; write migrations only after schema review.

## Singleton Discord gateway design
Every deployed node runs a lightweight standby supervisor; **only the lease owner** connects the bot's Discord gateway session and registers active background tasks. PostgreSQL transactionally acquires/renews the lease using database time and returns a monotonically increasing fencing generation. Default candidate parameters borrowed from BF4SW: 30s TTL, 10s renew, 60s stale-node threshold, 1s standby poll, 5s DB timeout; tune after tests. On failed renewal, DB outage, loss of capability, draining, or expired local monotonic deadline, disconnect and cease leadership-only work immediately. A stale node cannot regain authority with an old generation. Startup must not assume that the presence of a token makes a node leader.

Discord's gateway reconnect/resume behavior, lease takeover and graceful logout must be validated to avoid simultaneous live sessions. Fencing is enforced for **all bot-owned database writes and singleton tasks**; a DB lease alone cannot guarantee that an already-disconnected or partitioned process has stopped sending Discord API requests, so avoid irreversible side effects and test split-brain recovery.

## BF4SW features to adapt selectively
- Eligible node selection, draining, capability checks, priority-based handoff, explicit operator handoff.
- PostgreSQL-backed runtime settings, audit trails, structured errors and deduplicated operator events.
- Per-guild configuration, bounded caches, Discord slash command registration, controlled reconnect/backoff.
- Docker deployment, health checks, migration gates, deterministic failure tests, standby/primary soak.
Do not copy BF4SW's server-monitoring tables, keeper scheduling, VPN-specific rules, or Battlelog-facing code.

## Read path and response design
The bot fetches existing player snapshots and **published** ranking generations from the statistics DB using read-only queries. No write-back and no collector refresh requests, including through alternate credentials or API proxies. Identity is platform + persona ID, and exclusions must be applied before returning search, autocomplete or leaderboards. Timestamp game-statistics collection and ranking publication separately. Presentation/embeds are deliberately **TBD pending user screenshots**; implement reusable data-transfer models so Discord presentation can change without rewriting SQL.

## Testing before deployment
- Test read-only statistics credential by explicitly attempting prohibited writes and confirming permission denial.
- Exercise acquire/renew/release with two and three contenders; crash, network partition, delayed DB query, clock skew, PostgreSQL failover, forced handoff, and reconnect.
- Verify no simultaneous active command processing after controlled failover, no stale-generation writes, no command duplication for idempotent jobs.
- Validate guild settings persistence and isolation, migration upgrade/downgrade, Discord rate limits, autocomplete bounds, excluded player filtering, and website parity.
- Canary guild and long soak before public rollout.

## Decisions still needed
Bot name, priority beyond the initial pair, desired admin handoff controls, command scope, screenshots/embeds, whether public-stat reads use restricted SQL views or a strictly read-only API. The approved initial HA pair is rnt-01 preferred leader and mak-01 standby, with eventual deployment to all BF4SW Docker fleet nodes. See [HA-first rollout](DISCORD-BOT-HA-ROLLOUT.md). The separate `bf4ps_discord` control-plane database is deployed, and MAK-01/RNT-01 have demonstrated leader failover. Uncompleted fault-injection and soak tests remain open.
