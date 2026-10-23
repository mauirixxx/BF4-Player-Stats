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

## Production manual refresh integration (2026-10-22, card-v28)

- Discord /pstats player has an enabled **Refresh Stats** interaction on Overview, Weapons, and Vehicles, in both shareable-image and native Web (experimental) output. The button acknowledges privately (ephemeral) and reports accepted, cooldown, up-to-date, excluded, missing, or backend failure. A queued response is **not** proof collection has completed.
- Bot statistics database credentials remain strictly read-only. Manual requests use `discord-bot/bf4ps_discord/manual_refresh.py` and the separately authenticated TCOU manual-request service; the bot does not write to stats tables.
- Production endpoint: `http://192.168.10.71:8789/manual/request`, reached across the existing private IPsec network from RNT-01 (`192.168.200.47`) and MAK-01 (`192.168.10.70`). TCOU's service also retains its localhost listener `127.0.0.1:8789` for the website PHP gateway. The API checks caller IP, private token, allowed Origin, JSON shape, and database eligibility. It is **not** a public endpoint; preserve private-network and perimeter access controls.
- Bot container runtime requires `BF4PS_REFRESH_API_URL`, `BF4PS_REFRESH_API_ORIGIN`, and `BF4PS_REFRESH_API_TOKEN` from a private host-side `refresh.env` (mode 0600). Never commit or print the token. Deploy both HA nodes with both `--env-file .env` and `--env-file refresh.env`; retain node-specific `NODE_ID` and HA lease fencing. Image: `bf4ps-discord:card-v28`.
- The API implementation is `website/api/manual_request_api.py`. Its two listeners and source allowlist were deployed to TCOU and synchronized to GitHub main. This is a site-specific binding; adapt interface addresses and authorized peers when relocating hosts. Website and Discord share the existing collector budget, deduplication and manual cooldown; never bypass the dispatcher.
- Verification: both bot nodes successfully submitted authenticated requests for a nonexistent persona and received `not_registered` without creating jobs. RNT-01's Discord leader successfully connected (four guilds, zero restarts). The operator clicked the button for `mauirixxx` and received `Stats refresh queued!` in Discord, confirming a live accepted request. Collector completion after that request has not yet been independently verified.
- Important Discord lifecycle caveat: these buttons use `discord.ui.View(timeout=None)` on outgoing messages but **do not have registered persistent component handlers** after bot restart. New messages work; pre-restart buttons may stop working until persistent views or a routed custom-ID handler are implemented. Treat this as a follow-up, not a verified persistent-button feature.
