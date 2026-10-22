# BF4PS Discord Bot — Architecture and Implementation Plan
Status: living design; HA control plane and `/ping` deployed 2026-10-22. Statistics query contracts remain proposed and require live-schema validation.

## Goal and boundaries
A separately deployed Discord application for fast BF4 player and equipment statistics and platform-aware rankings. The statistics database is strictly read-only to this bot; its own separate bot-operations database stores coordination and guild settings. See [dedicated control-plane design](DISCORD-BOT-CONTROL-PLANE-DESIGN.md). The existing BF4PS PostgreSQL database and precompute generations remain authoritative. The bot does not scrape Battlelog, calculate rankings on request, or write directly to collector tables. Keep BF4SW and BF4PS bots independent: separate Discord application/token, processes, DB roles, configuration, deployment, and failure domains.

## Lessons carried forward from BF4 Server Watcher
- Slash commands first; avoid message-content privileged intent and prefix parsing by default.
- Durable guild configuration in PostgreSQL, not process memory; idempotent migrations and strict schema contracts.
- One primary bot process initially, Dockerized with health reporting and graceful shutdown; add HA only after single-instance behavior is proven. Multiple Discord gateway connections can duplicate event work unless coordinated.
- Use structured errors, audit logging, bounded timeouts, retries with backoff and jitter, and safe interaction acknowledgement/defer within Discord's response deadline.
- Avoid high-frequency polling. Read existing snapshots; respect collector traffic budgets and refresh queue policy.
- Fail closed on missing DB permissions or stale schema; never leak secrets, tokens, private identities, or excluded players.

## Data flow
Discord interaction -> command handler -> read-only BF4PS query/service layer -> current published generation and soldier snapshots -> embed with explicit platform and last-updated timestamp -> Discord response.
No manual refresh or collector queue writes from this bot. All BF4PS statistics access is read-only.

## Proposed v1 commands (subject to approval)
- `/stats player:<name> platform:<pc|xboxone|ps4|auto>`: soldier overview, data freshness, direct website link. For ambiguous names, offer a select menu instead of guessing.
- `/weapon player:<name> item:<weapon> platform:<...>`: weapon statistics and available ranking from *published* generation.
- `/vehicle player:<name> item:<vehicle> platform:<...>`: vehicle statistics and available ranking.
- `/leaderboard type:<weapon|vehicle> item:<...> metric:<kills|kpm|accuracy> platform:<pc|xboxone|ps4|all>`: bounded top 10 from existing precomputed results, not a fresh full-population sort.
- `/platoon name:<...>`: only after verifying current platoon schema, discovery completeness, and user-facing semantics.
- `/help`, `/about`, `/health` (non-sensitive health summary).
Future: Discord-account-to-soldier linking with proof of control; saved favorites; guild subscriptions and scheduled posts. No automatic cross-platform identity merging.

## Correctness and privacy contracts
- Persona ID + platform is the canonical identity; display names and aliases are mutable. Resolve ambiguity interactively and never infer account linkage across platforms.
- Respect the production exclusion policy in **every** lookup, autocomplete, and ranking. Prefer DB-enforced, restricted views/functions rather than duplicating filtering logic in Discord code.
- Display collection timestamp and ranking generation timestamp separately. Explain that ranks are accurate for the published snapshot, not necessarily current Battlelog.
- Read only *published* generations; never expose partial builds. For absent ranking generation, say 'not yet computed', not zero rank.
- Autocomplete/search must be bounded and indexed. Paginate results, cap embeds, and prevent arbitrary user SQL.
- Guild-level permissions for configuration; public stats commands should not require Administrator privileges. Never expose admin-console privileges through the bot.

## PostgreSQL security
Create a dedicated `bf4ps_discord_readonly` role with narrowly scoped EXECUTE on audited read-only functions or SELECT on purpose-built filtered views; no general table SELECT, no DDL, no writes, no bypass of exclusion policy. Use a separate bot-owned PostgreSQL database and role for HA leadership and guild configuration.
Use `db.bf4statusbot.com` (or deployment-approved failover DNS), TLS as supported, short connect/query timeouts, and a small bounded pool. Validate role grants and query plans against the live schema before shipping.

## Runtime and observability
Python with discord.py 2.x, SQLAlchemy/psycopg as already standardized by BF4PS; pinned dependency versions, Docker image, unprivileged runtime, env-based secrets. Keep Discord gateway heartbeat independent of blocking DB operations. Cache immutable published-generation lookups briefly, invalidate by generation ID, and include stale-data timestamps. Structured logs with command, latency, cache status, errors, and anonymized guild/user IDs; no tokens or raw secrets. Add /health and metrics, restart-safe lifecycle, optional canary guild command registration.

## Implementation phases and gates
1. **Design and schema verification:** review authoritative `docs/database-schema.md`, `docs/operational-schema.md`, and live PostgreSQL; document exact soldier, alias, exclusion, equipment, ranking, platoon query contracts. Confirm bot naming and initial commands.
2. **Read-only prototype:** isolated app/token, one host, canary guild, `/stats` and `/help`; measure p50/p95 query and interaction latency.
3. **Equipment and leaderboards:** published-generation-only queries, bounded Top 10, autocomplete, platform disambiguation; verify parity with website.
4. **Hardening:** least-privilege role, migrations for guild settings only if needed, audit and error reporting, timeout/failover tests, restart/reconnect soak, Docker deployment.
5. **Dedicated control plane:** deploy bot-owned database, Alembic migrations, lease-fenced leader/standby nodes, handoff, and operational dashboards.
6. **Expansion:** platoons, saved favorites, notifications, and HA only when justified.

## Acceptance criteria for v1
No Battlelog HTTP traffic from bot; excluded identities never appear; zero DB writes by read-only commands; no duplicate cross-platform merges; no full-cohort ranking query per Discord interaction; missing/outdated data explicitly labeled; DB outage responds gracefully; published rankings match website; canary soak and restart pass; schema and operations documentation updated with exact grants and deployment procedures.

## Open decisions
Bot application name and avatar; command naming; which platforms and platoon features ship first; primary and standby hosts; whether restricted SQL or a strictly read-only API is the statistics read path. Discord embed layout awaits user screenshots. **Do not create Discord application credentials or production DB privileges before review.**

## Implementation status (2026-10-22)
The initial HA-first implementation supersedes the historical phase ordering above: `bf4ps_discord` control-plane database, two-node RNT/MAK lease-fenced supervisor, real Discord Gateway failover, Docker restarts, and operator-tested ephemeral `/ping` are deployed. The player-statistics read path, embed design, and commands remain unimplemented. See [HA rollout and evidence](DISCORD-BOT-HA-ROLLOUT.md). Current development proceeds on `main`.

## Guild management requirements — approved for design, not yet implemented (2026-10-22)
The operator requests management features modeled on BF4 ServerWatcher. Implement these before player-statistics commands, following live bot-owned schema verification and migration-first workflow.

1. **Minimum command-use role:** default **Everyone** (no additional role restriction), optionally set one Discord guild role as the minimum required role for ordinary bot commands. Define role hierarchy semantics and behavior when a configured role is deleted. Management commands must not be blocked by the ordinary-use restriction for an authorized manager.
2. **Management role:** default **guild owner**, optionally configure a guild role permitted to administer bot settings. The guild owner must retain unconditional recovery authority even after a management role is configured. Never assume that Discord Administrator alone overrides an explicit owner-only default without approval.
3. **Dedicated listen channels:** default **all eligible channels**. Allow an explicit set of channels; when the last configured channel is removed, automatically revert to the unrestricted default. Apply channel restrictions consistently to ordinary commands while keeping a documented management/recovery path.
4. **Dedicated command audit log channel:** default **none** (logging disabled). When set, send a timestamped audit message for each command invocation, including Discord user's **current display name**, immutable user ID, command name and sanitized options/target, guild and channel context, result (success/failure), and elapsed milliseconds. Example evidence: BF4SW command audit embeds for `/operator status` and `/playerhistory` with SUCCESS, result `ok`, duration, and target. Do not expose credentials, secrets, sensitive options, or excluded player identities. Decide whether to include denied/failed commands and how to handle log-channel send failures during implementation; command execution should not be blocked by audit-delivery failure.

### Planned management command interface (names provisional)
Historical initial suggestion (superseded by the confirmed `/admin` namespace below): a `/settings` slash-command group with subcommands for viewing effective settings, setting/clearing minimum role, setting/clearing management role, adding/removing/listing listen channels, and setting/clearing log channel. Require server-side authorization and audit changes. Persist guild settings in the separate `bf4ps_discord` database, never in the read-only player-statistics database. Validate Discord role/channel IDs and deleted resources; migrations, exact command names, and UI are pending discussion. Do not implement until the BF4SW outage is resolved and the operator resumes design.

### Confirmed command namespace and authorization (2026-10-22)
- Management slash commands live under **`/admin`**, not `/settings` or `/operator`. Include **`/admin status`**, modeled on BF4 ServerWatcher's `/operator status`, showing leader/standby, generation and lease health, uptime/version, database health, and effective guild settings. Only report verified runtime values; clearly mark unavailable telemetry.
- All `/admin` subcommands are **guild-owner-only by default**. Once a management role is configured, users holding that role **or any higher role in the guild role hierarchy** may administer settings. The guild owner **always** retains override/recovery access. Discord's Administrator permission alone is not a bypass. Perform authorization server-side on every interaction; handle deleted roles and absent guild context safely. Management access is independent of the ordinary minimum-role/listen-channel restrictions.
- Proposed management command groups: `/admin status`, `/admin minimumrole`, `/admin managementrole`, `/admin listenchannel`, `/admin logchannel`. Exact set/clear/add/remove option shapes remain to be finalized; these are design requirements, not deployed commands.
- Player-facing slash commands live under **`/pstats`**, **not `/stats`**, to avoid collision/confusion with another Battlefield stats bot. Candidate subcommands `/pstats player`, `/pstats weapons`, `/pstats vehicles` remain pending design and schema verification. The existing `/ping` is a standalone diagnostic command until explicitly changed.
- Guild owner override must permit recovery from bad configuration. Compare Discord role positions appropriately (including tie handling), not merely role IDs or permission flags. Audit denied management attempts where an audit channel is configured, without exposing sensitive data.
