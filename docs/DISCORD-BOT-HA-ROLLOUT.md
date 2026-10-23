# BF4PS Discord Bot — HA-First Rollout
Status: initial two-node HA deployed and live Discord Gateway tested, 2026-10-22. Historical planning and uncompleted validation gates remain below.

## Fixed decisions
- A new Discord application independent of BF4SW.
- BF4PS statistics database access is **strictly read-only**, with a dedicated role. The bot's own separate PostgreSQL database stores leases, nodes, configuration, and operational state.
- All nodes in the existing BF4SW Docker fleet are eventual BF4PS Discord bot deployment targets, each running an independent bot container.
- **Initial HA pair:** `rnt-01` preferred leader; `mak-01` first failover candidate. All other nodes stay uninstalled until HA and user-facing commands are validated.
- **HA functionality precedes statistics commands and embeds.** Result presentation awaits user screenshots.
- Use BF4SW control-plane implementation as reviewed reference, not blindly copied code.

## First implementation milestone: infrastructure only
1. Verify current BF4SW Docker fleet membership, actual site/host names, live lease logic, and the existing PostgreSQL cluster's current primary and permissions.
2. Create `bf4ps_discord` database with a dedicated migration owner and a least-privileged bot operations role; Alembic revision 0001 includes node registration, capabilities, lease/generation fencing, runtime settings, handoff requests, and operator events. Never reuse BF4SW tables or credentials.
3. Implement Python bot leadership supervisor using PostgreSQL server-time leases, generation fencing, conservative monotonic local expiry, bounded DB operations, heartbeat, drain state, and leader-only Discord gateway connection.
4. Docker image and Compose/systemd integration for `rnt-01` and `mak-01`, restart policies, secret environment files, structured logs, health checks, and startup migration compatibility check.
5. Start with no public statistics commands; optionally a tightly scoped development-only `/health` command after gateway connectivity is confirmed.

## Election and failover rules
- Single lease key `discord:leader`, 30s default TTL and 10s renew; one active gateway owner; every other node runs a standby supervisor without Discord gateway connection.
- Preferred order RNT then MAK for initial acquisition, but **no automatic preemption** of a healthy incumbent when a preferred node returns. Explicit handoff or loss of eligibility transfers ownership.
- On lease loss, DB uncertainty, stale capability, or local authority expiry, stop leader-only operations and disconnect the gateway; standby must acquire a new fenced generation before connecting.
- The database and gateway are distinct failure domains. Test delayed Discord disconnect and old gateway sessions: DB fencing alone cannot make remote Discord calls impossible.
- HA uses existing PostgreSQL failover DNS; re-establish sessions after DB failover and revalidate generation before any leader-only operation.

## Validation gates before commands
- Simultaneous start of RNT and MAK yields exactly one lease owner and one connected Discord session.
- Stop/kill RNT process and Docker container: MAK automatically becomes leader within the documented TTL/retry bound.
- Bring RNT back: it remains standby while MAK is healthy (no flapping).
- Stop/kill MAK: RNT takes over.
- Exercise controlled handoff in both directions; stale-generation write attempts are rejected.
- Inject DB disconnect, query delay, clock skew, network partition, Discord gateway disconnect, and PostgreSQL primary failover; prove safe recovery and document any duplicate-session window.
- Restart/reboot both hosts; verify Docker auto-start, DB migrations, and persistent node settings.
- Soak for at least 24h with leadership event log, gateway reconnect counts, DB connection count, and lease renewal health; only then add player-stat commands.

## Fleet expansion gate
After commands and embed designs are usable, build once and deploy the same pinned image to the full verified BF4SW node inventory. Nodes register their stable IDs, site, and explicit priority; enable one at a time. Do not assume all sites are equally reachable or that priority implies immediate preemption. Keep manual drain and handoff capability.

## Open implementation questions
Exact node priority beyond RNT and MAK, Discord application name/token, initial development guild, operational alert destination, and preferred operator handoff interface. None blocks writing migrations and an offline HA test harness.

## Actual deployment and test record — 2026-10-22
- Independent Discord application `BF4 Player Stats#4096` invited to the initial development server; operator confirmed `/ping` responds ephemerally and supplied screenshots.
- Production control-plane database: `bf4ps_discord`, separate from the BF4PS statistics database. Initial nodes: `rnt-01` and `mak-01`; containers `bf4ps-discord-ha-rnt` and `bf4ps-discord-ha-mak` respectively, images `bf4ps-discord:ha-ping`, `DRY_RUN=0`.
- Both nodes configured with Docker `--restart unless-stopped`; **host reboot behavior not yet verified**. Secrets are in host-local `/opt/bf4ps-discord/discord-bot/.env` and must not enter Git.
- Observed database outage: RNT suspended leadership when PostgreSQL was shutting down; MAK later reacquired leadership generation 4 after recovery (dry-run mode). This was observed in logs, not an orchestrated partition test.
- Controlled graceful failover with real Discord Gateway: RNT generation 7 stopped at 07:06:43 UTC; MAK acquired generation 8 at 07:06:44 UTC, authenticated and emitted `discord_ready`. RNT rejoined standby without preempting the healthy incumbent.
- Following code deployment, RNT acquired generation 9, Discord reported `slash_commands_synced count=1`, connected Gateway and emitted `discord_ready`; MAK remained standby. Operator subsequently verified `/ping` interaction and private response.
- `/ping` checks authoritative `bot_leases` owner, generation, expiration, node enabled/draining before replying; errors fail closed. Command code committed as `c6947a7` on `main`.
- Remaining validation: ungraceful process kill, delayed network partition/lease expiration with an actual Gateway, DB primary failover while active, duplicate-session observation, host reboot, and long soak. **Do not mark these passed without test evidence.**
- Caution: current containers are running live; deployment changes must preserve a single leader. `/pstats player` is now deployed on both nodes; operator verified two player embeds. RNT acquired leadership generation 29 during the overview rollout, synchronized three top-level slash commands, and connected to the Gateway.

## Next milestone — player statistics commands
- Start with a read-only `/player` soldier lookup by player name and platform, subject to reviewing `docs/database-schema.md`, `docs/operational-schema.md`, and live schema first.
- Confirm restricted statistics DB read role and exclusions, use bounded indexed search, handle ambiguous names, and show data freshness and canonical platform/persona identity. No Battlelog requests or writes to collector DB.
- Add user-approved Discord embeds, test from development server, then equipment/leaderboard commands. Use `main` for rapid iteration per operator direction; no additional development branch required.

## Next feature priority update — 2026-10-22
Operator prioritized guild management settings and command auditing ahead of player lookup. Those features are now implemented; `/pstats player` detailed overview is also live. Both nodes use the dedicated read-only BF4PS statistics connection. Existing remaining HA fault-injection and soak gates are not claimed as passed.

## Production manual refresh integration (2026-10-22, card-v28)

- Discord /pstats player has an enabled **Refresh Stats** interaction on Overview, Weapons, and Vehicles, in both shareable-image and native Web (experimental) output. The button acknowledges privately (ephemeral) and reports accepted, cooldown, up-to-date, excluded, missing, or backend failure. A queued response is **not** proof collection has completed.
- Bot statistics database credentials remain strictly read-only. Manual requests use `discord-bot/bf4ps_discord/manual_refresh.py` and the separately authenticated TCOU manual-request service; the bot does not write to stats tables.
- Production endpoint: `http://192.168.10.71:8789/manual/request`, reached across the existing private IPsec network from RNT-01 (`192.168.200.47`) and MAK-01 (`192.168.10.70`). TCOU's service also retains its localhost listener `127.0.0.1:8789` for the website PHP gateway. The API checks caller IP, private token, allowed Origin, JSON shape, and database eligibility. It is **not** a public endpoint; preserve private-network and perimeter access controls.
- Bot container runtime requires `BF4PS_REFRESH_API_URL`, `BF4PS_REFRESH_API_ORIGIN`, and `BF4PS_REFRESH_API_TOKEN` from a private host-side `refresh.env` (mode 0600). Never commit or print the token. Deploy both HA nodes with both `--env-file .env` and `--env-file refresh.env`; retain node-specific `NODE_ID` and HA lease fencing. Image: `bf4ps-discord:card-v28`.
- The API implementation is `website/api/manual_request_api.py`. Its two listeners and source allowlist were deployed to TCOU and synchronized to GitHub main. This is a site-specific binding; adapt interface addresses and authorized peers when relocating hosts. Website and Discord share the existing collector budget, deduplication and manual cooldown; never bypass the dispatcher.
- Verification: both bot nodes successfully submitted authenticated requests for a nonexistent persona and received `not_registered` without creating jobs. RNT-01's Discord leader successfully connected (four guilds, zero restarts). The operator clicked the button for `mauirixxx` and received `Stats refresh queued!` in Discord, confirming a live accepted request. Collector completion after that request has not yet been independently verified.
- Important Discord lifecycle caveat: these buttons use `discord.ui.View(timeout=None)` on outgoing messages but **do not have registered persistent component handlers** after bot restart. New messages work; pre-restart buttons may stop working until persistent views or a routed custom-ID handler are implemented. Treat this as a follow-up, not a verified persistent-button feature.
