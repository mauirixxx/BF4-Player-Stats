# BF4PS contingency: migrate PostgreSQL primary to TrueNAS (planning only)

**Status:** DRAFT / NOT APPROVED FOR EXECUTION. No topology changes authorized. Prepared 2026-11-17.

## Goal and proposed topology

Move the complete **BF4 Player Stats** PostgreSQL database from production primary `mak-db-02` to an isolated PostgreSQL instance on the unused TrueNAS host **192.168.10.66** on the Makawao LAN. The TrueNAS host has an eight-core Atom CPU, 64 GiB RAM, 10 GbE, and 40+ TB usable storage (capacity, disk layout, IOPS, ZFS configuration, and actual free space require verification). `tcou` (192.168.10.71) and `mak-db-02` are on the same 10 GbE LAN. Existing `*-db-01` and `mak-db-02` nodes would cease hosting BF4PS only after cutover and validation, and continue BF4SW where applicable.

**Major tradeoff:** single BF4PS PostgreSQL server removes synchronous/asynchronous replica resilience. TrueNAS storage redundancy is **not** a substitute for independent backups or point-in-time recovery. A failure of the TrueNAS host or its LAN path would take down BF4PS until restoration. Keep at least one off-host, off-pool backup copy, preferably offsite.

## Known state and verification gates

- Current PostgreSQL primary: `mak-db-02`; BF4PS database: `bf4_playerstats`. Streaming replicas include `mak-db-01`, `hnl-db-01`, `kah-db-01`, `rnt-db-01`; verify current roles, health, and BF4SW co-location.
- Compact ranking uses `equipment_rank_generations`, `equipment_rank_compact_blocks`, `equipment_rank_compact_lookup`, and `equipment_rank_compact_published`. At planning time compact storage ~405 GB and the primary ~66 GiB free; figures change.
- 2026-11-17 snapshot: 2,624 live published compact scope pointers, 14,425 generations (5,248 format-2 published, 6,476 format-2 validated, 2,640 format-1 published, 60 format-1 retired, 1 failed). This is a diagnostic snapshot, **not** an authorization to delete rows.
- The TrueNAS MariaDB Docker container **was used for BF4CR archival/export work** in October 2026: container `ix-mariadb-mariadb-1` (image `mariadb:13.0.2`), with persistent data mounted under `/mnt/.ix-apps/app_mounts/mariadb/data` and BF4CR downloads under `/mnt/deep-pool/bf4cr-downloads`. It was used to query/export the `brs` database; whether any current clients still use it is **not verified**. Inventory volumes, databases, owners and clients before changing it; do not delete it on an assumption of disuse. PostgreSQL must be deployed separately; MariaDB cannot directly host this PostgreSQL database.
- Verify TrueNAS CPU performance, 10 GbE throughput, ZFS pool health, usable space, IOPS/latency, ARC memory budget, UPS/power, TrueNAS release, supported PostgreSQL deployment approach, container/VM persistence, dataset properties, snapshot policy, and host security.
- Verify production PostgreSQL **major version**, extensions, locales/collations, encoding, role definitions, ownership, privileges, replication slots, tablespaces, `pg_hba.conf`, server parameters, and **current Alembic head**. Consult `docs/database-schema-reference.md` and the complete current `player-collector/migrations/versions/` before schema-dependent queries or code. Reconcile documentation vs migrations before proceeding.

## Phase 0: Inventory and readiness (no downtime)

1. Inventory every BF4PS writer, reader, collector, ranking publisher, retention service, discovery sync, website, admin route, Discord bot, cron/systemd timer, external integration, monitoring agent, and backup job. Record host, service, current database endpoint, credential source, and restart order. Include the BF4BR→BF4PS and BF4SW→BF4PS discovery feeds.
2. Confirm which services share the PostgreSQL cluster with BF4SW and what would be affected by changing `pg_hba.conf`, replication, or removing the BF4PS database.
3. Baseline data size, relation sizes, row counts/checksums on selected critical tables, extensions, roles, indexes, sequences, constraints, publication pointers, job queues, WAL generation, replica lag, and free space. Save timestamped results.
4. Benchmark a **scratch** PostgreSQL instance on TrueNAS using representative ranking read/write/retention and collector workload. Confirm CPU, IOPS, fsync latency, WAL behavior, memory, and end-to-end query performance; 10 GbE alone does not guarantee database performance.
5. Choose a supported PostgreSQL 16-compatible runtime and durable storage; test automatic start, safe shutdown, backup/restore, alerting, TLS and host firewall. Confirm the PostgreSQL major version matches or define a separately tested upgrade path.
6. Estimate downtime and transfer time using a full-size rehearsal. Decide whether to use an offline physical base backup/cluster copy, `pg_basebackup`, or logical `pg_dump`/`pg_restore`; do **not** mix file-level copies of a running database with logical consistency assumptions. For a database-only migration from a shared cluster, logical backup/restore is often preferable, but may take longer and requires roles/extensions/privileges and sequence checks. Physical copy/base backup is cluster-wide and includes BF4SW; removing other databases afterward adds risk. Choose only after inventory.
7. Establish a **tested rollback** and a backup that can be restored independently of both old and new primary. Reserve enough space for at least one extra full database copy, WAL and working files.

## Phase 1: Backup and PITR design (before cutover)

1. Create scheduled **physical base backups** of the new PostgreSQL cluster plus continuous **WAL archiving** to an independent destination. PostgreSQL does not provide native arbitrary incremental `pg_dump`; for incremental physical backups use a version-compatible, proven tool such as pgBackRest or Barman, with tested full/differential/incremental strategy and WAL retention.
2. Backups must reside on a separate failure domain, not merely another directory/dataset on the same TrueNAS pool. Replicate encrypted backups off-host/offsite and protect credentials.
3. Define RPO/RTO, retention, immutable/offline copies, backup encryption, alerting on failed backup/WAL archival, and periodic automatic restore tests. ZFS snapshots can complement backups but do not replace WAL/PITR and independent copies.
4. Perform a real point-in-time restore to an isolated test PostgreSQL instance and run application-level integrity checks.

## Phase 2: Pre-cutover controls

1. Announce a maintenance window and create a freeze on BF4PS deployments, schema changes, and ranking publications.
2. Put the BF4PS website/API and Discord-facing commands into maintenance/read-only mode **without** interrupting BF4SW or BF4BR independently.
3. Stop/drain all BF4PS writers: collectors, ranking publishers, retention/GC, discovery/identity sync, administrative write jobs, Discord write paths, scheduled tasks, and any external workers writing BF4PS. Disable automatic restarts/timers temporarily.
4. Verify zero BF4PS write connections and in-flight transactions, no active migrations, and no uncommitted transactions. Record final LSN, schema revision, counts, role grants, and application health. Keep old PostgreSQL primary available as a **frozen rollback source**.
5. Take and verify a final consistent backup or migration snapshot; do not delete old data.

## Phase 3: Copy and verify

1. Transfer with a documented, resumable, integrity-checked method over the 10 GbE LAN. For a logical migration, restore roles/global objects separately as appropriate, then the full `bf4_playerstats` database. For a physical approach, follow PostgreSQL-supported cluster-wide procedures and account for BF4SW data explicitly.
2. Verify PostgreSQL starts cleanly and all expected extensions, schemas, tables, indexes, sequences, constraints, functions, ownership, privileges, and Alembic revision match.
3. Compare source vs destination **consistent snapshots**: exact counts of critical entities, scope pointers, ranking generations, data integrity hashes or ordered checksums on representative and high-risk data, sequence next values, foreign keys, and query results. PostgreSQL file byte equality is not required for logical restores; '100% duplication' means logically equivalent complete data and application behavior.
4. Run read-only smoke tests for website, leaderboard/search, admin dashboards, Discord, collectors' DB access, retention dry-run, and discovery endpoints against the new database. Check query plans and latency.
5. Do not drop BF4PS from any old node yet. Set a signed-off go/no-go checkpoint.

## Phase 4: Cutover and staged restart

1. Update centralized DB endpoint/secret references for every BF4PS service, firewall allowlists, TLS certificates, monitoring, and backups. Avoid exposing PostgreSQL publicly.
2. Bring up the website/readers and verify read-only correctness. Start a single controlled writer and verify transaction commit, WAL archiving, and read-back.
3. Restart discovery, collectors, Discord bot, retention, and ranking publishers in controlled groups, verifying each class. Use a one-publisher canary before full ranking throughput; watch disk, CPU, memory, ZFS I/O latency, WAL and PostgreSQL locks.
4. Exit maintenance only after application and data checks pass. Record the new authoritative DB endpoint and update runbooks, configuration inventories, and disaster recovery instructions.

## Phase 5: Stabilization and delayed retirement

1. Maintain the old BF4PS database **read-only and intact** for a defined rollback period. Do not permit split-brain writes. Rollback after new writes requires a tested reverse migration or loss/replay plan; simply pointing clients back is unsafe.
2. Observe multiple complete collector and ranking cycles; verify retention and backup/PITR restores under real load.
3. After explicit operator approval, verified independent backups, and expired rollback window, remove **only BF4PS** databases/replication artifacts from the former cluster/replicas. Audit BF4SW dependencies, replication slots, WAL retention, and shared roles first. Deleting a database on a primary may replicate the drop to physical standbys; never assume each replica is independently writable.
4. Reclaim old disks and return the former hosts to BF4SW-only duties after confirming no shared objects were lost.

## Rollback gates and stop conditions

Stop immediately for: inconsistent data, missing privileges/extensions, poor benchmark results, unverified backups, unexpected BF4SW impact, lack of off-host restore, excessive WAL or I/O latency, replication/recovery uncertainty, or unaccounted writers. **Never delete the old BF4PS copy as part of the initial cutover.**

## Storage reclamation note

Moving to TrueNAS increases headroom but does not inherently shrink PostgreSQL compact relation files. Fix obsolete-generation retention first. After migration and independent backups, plan measured reclamation of bloated TOAST/index storage (e.g., supported table rewrite or `pg_repack` where appropriate), budgeting extra disk and WAL and testing on a clone. Do not run `VACUUM FULL` on the nearly full current primary.

## Open decisions

- Is TrueNAS Atom CPU/ZFS latency sufficient for the ranking workload?
- Is a single DB host acceptable versus one low-cost off-host PostgreSQL replica?
- Which backup destination, PITR retention, and recovery objectives?
- Which PostgreSQL deployment model is supported on this TrueNAS release?
- Does the MariaDB container still serve any clients or retained BF4CR export workflow?
- Which migration method meets the acceptable downtime?
- How long to retain the old frozen cluster before destructive cleanup?


## Appendix A: observed service inventory (live audit, 2026-11-17 22:39–22:42 UTC)

**Evidence standard:** These names were observed through read-only `systemctl list-units`, `systemctl list-timers`, and `docker ps` on the named hosts. They are **not yet a complete dependency graph**: verify each unit's `ExecStart`, `EnvironmentFile`, drop-ins, Docker compose/stack owner, DB target, auto-restart policy, and whether it actually writes BF4PS. Never assume a service can be stopped merely because it contains 'bf4'. Avoid touching shared BF4BR/BF4SW services.

| Host | Observed BF4PS processes, containers, and units | Proposed migration disposition (verify before executing) |
| --- | --- | --- |
| mak-01 | Docker `bf4ps-production-collector`, `bf4ps-compact-ranking`, `bf4ps-discord-ha-mak`; systemd `bf4ps-compact-ranking.service`, `bf4ps-compact-retention.service/.timer`, `bf4ps-rank-gc.service/.timer`, `bf4ps-vacuum-watch.service/.timer`, `bf4ps-watchdog.service/.timer`, `bf4ps-weapon-metrics-sync.service` (failed at audit), `bf4ps-compact-ranking-resume.service/.timer` | Drain/stop collector, publisher, Discord write paths, retention/GC, metric sync, watchdog/auto-resume; distinguish read-only vacuum watch; inventory restart policies |
| mak-02 | Docker `bf4ps-production-collector`, `bf4ps-compact-ranking`, `bf4ps-vehicle-metrics-sync`; systemd `bf4ps-compact-ranking.service`, `bf4ps-vehicle-metrics-sync.service`, `bf4ps-compact-ranking-resume.service/.timer` | Stop collector, publisher, vehicle metric reconciliation, and auto-resume |
| mak-03 | Docker `bf4ps-production-collector`, `bf4ps-compact-ranking`; systemd `bf4ps-compact-ranking.service`, `bf4ps-compact-ranking-resume.service/.timer` | Stop collector, publisher and auto-resume |
| mak-04 | Docker `bf4ps-production-collector`, `bf4ps-compact-ranking`; systemd `bf4ps-compact-ranking.service`, `bf4ps-compact-ranking-resume.service/.timer` | Stop collector, publisher and auto-resume |
| mak-05 | `bf4ps-platoon-alternating.service/.timer` | Drain platoon roster/discovery and disable timer |
| hnl-01 | Docker `bf4ps-production-collector` | Drain collector and inspect restart policy |
| hnl-02 | **Inventory unavailable** (remote command failed) | **BLOCKER:** inspect host directly before cutover |
| hnl-03 | Docker `bf4ps-production-collector`; `bf4ps-platoon-alternating.service/.timer` | Drain collector and platoon timer |
| kah-01 | Docker `bf4ps-production-collector` | Drain collector |
| rnt-01 | Docker `bf4ps-production-collector`, `bf4ps-discord-ha-rnt`; PostgreSQL scratch `postgresql@16-bf4psscratch.service` | Drain collector/Discord writes; preserve independent scratch database unless separately approved |
| tcou | `bf4ps-admin-api.service`, `bf4ps-discovery.service`, `bf4ps-leaderboard-api.service`, `bf4ps-manual-api.service`, `bf4ps-platoon-submit.service`, `bf4ps-bf4br-sync.service/.timer`, `bf4ps-community-export.service/.timer`, `bf4ps-graphs-export.service/.timer`, `bf4ps-homepage-summary.service/.timer`, `bf4ps-platoon-emblem-cache.service/.timer`, `bf4ps-platoon-preview-images.service/.timer`, `bf4ps-share-preview-index.service/.timer`, `bf4ps-clear-ranking-notice.service/.timer`, plus `bf4-status-dashboard.service` and sampler | Maintenance-mode website, pause all write-capable APIs, identity/discovery sync and timed exporters; identify read-only services; inspect Apache/PHP-FPM and cron independently |
| mak-db-02 | `postgresql@16-main.service`, `bf4ps-disk-sample.service/.timer` | Freeze BF4PS writes only; **do not stop PostgreSQL** while BF4SW or replicas depend on it |
| mak-db-01 | `postgresql@16-main.service` running | Preserve cluster until cutover and rollback approval |
| hnl-db-01 | `postgresql@16-main.service` running | Preserve cluster until cutover and rollback approval |
| kah-db-01 | `postgresql@16-main.service` **inactive** at audit | Investigate actual role and availability; do not count as healthy replica |
| rnt-db-01 | `postgresql@16-main.service` running | Preserve cluster until cutover and rollback approval |
| reports | BF4BR scheduler, external API, feeder, deployer and backup services observed; **not BF4PS services** | Preserve BF4BR; check only any direct BF4PS integration/credential usage |

**Important:** The compact ranking `systemd` units and Docker containers on mak-01 through mak-04 were **active/running** at audit time, even though ranking publication had been described as paused. A WAL gate can suppress publication without stopping processes. Before migration, verify actual DB sessions and disable both the process and its auto-resume mechanism. `mak-01` also had an ephemeral test Docker container during the retention test; exclude such one-off containers from the permanent service manifest.

### A.1 Required second-pass audit (mandatory before executing migration)

For **every host** above, collect and commit a timestamped, redacted manifest with:

1. `systemctl list-unit-files`, `systemctl list-units --all`, `systemctl list-timers --all`, `systemctl cat <each BF4PS unit>`, `systemctl show -p FragmentPath,DropInPaths,ExecStart,EnvironmentFiles,Restart,PartOf,WantedBy`; capture enabled/disabled/masked and timer trigger semantics.
2. `docker ps -a`, `docker inspect` (redact environment secrets), compose project/working directory, bind mounts, named volumes, networks, restart policy, and Docker daemon/compose boot behavior; inspect **stopped** containers too. Do not confuse `bf4br-supervisor.service` or BF4SW containers with BF4PS.
3. User and root crontabs, `/etc/cron*`, `at` jobs, supervisor processes, custom scripts, and ad-hoc background sessions. Inventory systemd **user** units as well as system units.
4. PostgreSQL `pg_stat_activity` grouped by client IP, database user, application name and state, including idle sessions; cross-check against every known node. Identify hidden clients by network connection monitoring. Do not log credentials or connection strings.
5. Apache vhosts, PHP-FPM pools, CLI PHP jobs, website environment/config, private APIs, Discord HA election/leader logic, webhook consumers, remote external workers, BF4SW→BF4PS discovery, BF4BR→BF4PS identity sync, admin manual queues, and monitoring automations.
6. For each process mark **WRITE / READ / UNKNOWN**, current endpoint source, safe drain procedure, stop command, start command, startup dependencies, data-loss risk, and verification command. Any **UNKNOWN** is a no-go.
7. Explicitly distinguish BF4PS from BF4SW, BF4BR, BF4CR, ServerWatcher, MapWatcher, PlayerTracker and shared PostgreSQL instances. Maintain a dependency diagram and ordered stop/restart checklist, including services that automatically recreate stopped containers.

### A.2 Pre-cutover shutdown verification

- Disable auto-resume timers and job schedulers **first**, then drain active work; verify leases and checkpoints before stopping writers.
- Stop services through their **actual supervisors** (systemd, compose, Docker restart policy), not only `docker stop`. Record previous enablement state for restoration.
- Confirm no BF4PS write-capable sessions on `mak-db-02` across multiple samples; verify all expected nodes checked in as stopped.
- Keep read-only site maintenance and backup/monitoring functional where safe; do not accidentally shut down BF4SW or BF4BR.
- Obtain explicit operator approval after reviewing a machine-readable **all-green shutdown manifest**. Do not begin the final transfer if any host remains unverified.

## Appendix B: retention incident and measured fix (2026-11-17)

- The prior cleanup script only considered `published` format-2 generations. Many abandoned `validated` generations remained after publication gates/lease failures.
- New GitHub cleanup selector protects current pointers, two newest generations per scope, active job leases, legacy references, and validated generations younger than 24 hours. Requires a currently published pointer for the scope before deleting an older validated generation.
- Initial candidate dry runs timed out at 15 seconds; removing expensive block-existence probes from the selection scan produced a **9.62-second successful dry run**.
- **Single-generation canary:** generation `5190`, format 2, `validated` since 2026-11-04, 72 compact blocks. A bounded `--limit 1 --execute` test completed in **4.67 seconds**. Independent primary verification confirmed generation count 0, block count 0, and published pointer references 0 afterward. Replica replay backlog was ~22 GiB before and ~21 GiB afterward; this is not proof that deletion caused the reduction.
- This is a **one-generation validation**, not a validated bulk cleanup rate. Do not raise the production retention timer limit or install the candidate into the running service until additional tests and WAL/replica/TOAST monitoring are completed.
