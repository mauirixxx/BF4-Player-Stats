# BF4PS Infrastructure Watchdog — design baseline (2026-10-26)

Status: design only; NOT deployed or sending alerts. The administrator requested BF4SW-style notifications to all configured BF4PS administrators when nodes/services fail and when disks fill. This document is authoritative for implementation and should be reviewed before code changes.

## Monitoring boundaries
- Independent watchdog process, preferably two different failure domains (e.g. mak and hnl/rnt); never rely solely on the BF4PS Discord bot or production PostgreSQL to detect its own outage.
- Inventory explicit hosts and expected services; distinguish planned maintenance from failures. Monitor DB primary and every standby, website and admin APIs, Discord bot gateway/control plane, player and platoon collectors, rank builder, rank GC, and scheduled jobs. Heartbeat-based checks detect absent nodes; TCP/HTTP/service checks detect degraded-but-reachable nodes. Monitor external HTTPS from outside the website host.
- Monitor all relevant mounted filesystems (bytes and inodes) and PostgreSQL volume free space; distinguish capacity, disk-write errors, replication/WAL retention and expected transient WAL churn.
- Disk thresholds: warning >=80% used, critical >=90%, emergency >=95% OR <5 GiB free; recovery hysteresis >=5 percentage points below the alert threshold, configurable per filesystem. Also alert on sustained growth and predicted exhaustion when reliable samples exist. Never remove data automatically.
- Replication: primary reachability, expected primary count exactly one, standby recovery state, replay/receive lag and WAL retention. Treat failover transitions specially to avoid duplicate alerts.

## Delivery and administrators
- Dedicated private Discord incident channel plus direct messages to an explicit allowlist of Discord user IDs. Do NOT treat every guild administrator or management role holder as an infrastructure admin; those roles may be public/server-scoped. Add/remove BF4PS operations admins through an authenticated, audited management command with least privilege.
- Initial admin can be Discord user ID 328032141428654092 (owner confirmation required); adding other admins requires explicit consent and audit. Discord DMs can be disabled by recipients; private incident channel is the reliable fallback. Do not store bot tokens/webhook secrets in Git.
- Send OPEN, ESCALATED, RECOVERED; deduplicate by (node,check,resource); 2–3 failed probes before opening, bounded periodic reminders for unresolved critical events, and maintenance/silence windows with expiry. Avoid ping storms and leaking credentials, private IPs, or stack traces to public channels.
- Notification delivery must be independent of the service being monitored. If Discord itself is unreachable, spool bounded events locally and retry with backoff; consider an independent second transport for total Discord outage.

## State and HA
- Prefer a dedicated lightweight watchdog state store independent of the production stats DB, with leader lease/fencing or deterministic active/standby alert ownership. A single watchdog failure must itself be detectable by its peer. Persist incident state, acknowledgements, delivery receipts, check inventory, and bounded history; the user's cancellation of player-stat historical tracking does not require discarding operational incident audits.
- Per-node local health agents should publish heartbeat, disk and service status over authenticated channels; cross-node probes detect a dead agent/node. Protect agent endpoints, enforce timeouts, TLS/authentication, and rate limits. Never allow arbitrary shell commands from Discord.
- Include test probes, outage simulations, false-positive controls, deployment rollback, and an on-call test message before enabling live notifications.

## Open deployment decisions
1. Private Discord destination guild/channel ID (not yet provided).
2. Whether alerts should DM all admins in addition to the private channel; recommend both.
3. Initial admin allowlist and mechanism to enroll additional admins.
4. Second watchdog failure domain and inventory of expected nodes/services, validated live.

## Related storage incident and mitigation
On 2026-10-26 mak-db-01 and mak-db-02 ran out of disk and PostgreSQL 16 clusters failed. Virtual disks expanded to 232 GB and 190 GB, respectively, and online partition/LVM/ext4 expansion completed; PostgreSQL primary and standby restarted. BF4PS ranking results were the largest database consumer: approximately 79 GiB in equipment_rank_rows, including ~46 GiB indexes. At inspection there were 874 retired generations (~109M rows metadata), 2,624 published (~290M rows metadata), and one failed. The bounded rank GC was increased from 3 hourly to 5 every 5 minutes, with verified successful deletions and current published snapshots protected; see DISTRIBUTED-RANKING-WORKERS-DESIGN.md. The primary filesystem's free space subsequently rebounded to about 61.75 GiB; short-term WAL recycling is a possible but unconfirmed explanation for the fluctuation. Monitor capacity and WAL before attempting physical table compaction. Do not confuse deleting obsolete generations with shrinking relation files.
