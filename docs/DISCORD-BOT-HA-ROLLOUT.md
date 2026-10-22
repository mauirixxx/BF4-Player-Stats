# BF4PS Discord Bot — HA-First Rollout
Status: approved design direction, not deployment authorization. 2026-10-21.

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
