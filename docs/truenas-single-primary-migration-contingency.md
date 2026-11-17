# BF4PS contingency: migrate PostgreSQL primary to TrueNAS (planning only)

**Status:** DRAFT / NOT APPROVED FOR EXECUTION. No topology changes authorized. Prepared 2026-11-17.

## Goal and proposed topology

Move the complete **BF4 Player Stats** PostgreSQL database from production primary `mak-db-02` to an isolated PostgreSQL instance on the unused TrueNAS host **192.168.10.66** on the Makawao LAN. The TrueNAS host has an eight-core Atom CPU, 64 GiB RAM, 10 GbE, and 40+ TB usable storage (capacity, disk layout, IOPS, ZFS configuration, and actual free space require verification). `tcou` (192.168.10.71) and `mak-db-02` are on the same 10 GbE LAN. Existing `*-db-01` and `mak-db-02` nodes would cease hosting BF4PS only after cutover and validation, and continue BF4SW where applicable.

**Major tradeoff:** single BF4PS PostgreSQL server removes synchronous/asynchronous replica resilience. TrueNAS storage redundancy is **not** a substitute for independent backups or point-in-time recovery. A failure of the TrueNAS host or its LAN path would take down BF4PS until restoration. Keep at least one off-host, off-pool backup copy, preferably offsite.

## Known state and verification gates

- Current PostgreSQL primary: `mak-db-02`; BF4PS database: `bf4_playerstats`. Streaming replicas include `mak-db-01`, `hnl-db-01`, `kah-db-01`, `rnt-db-01`; verify current roles, health, and BF4SW co-location.
- Compact ranking uses `equipment_rank_generations`, `equipment_rank_compact_blocks`, `equipment_rank_compact_lookup`, and `equipment_rank_compact_published`. At planning time compact storage ~405 GB and the primary ~66 GiB free; figures change.
- 2026-11-17 snapshot: 2,624 live published compact scope pointers, 14,425 generations (5,248 format-2 published, 6,476 format-2 validated, 2,640 format-1 published, 60 format-1 retired, 1 failed). This is a diagnostic snapshot, **not** an authorization to delete rows.
- The TrueNAS MariaDB Docker container's purpose is **unknown**. Inventory its mounts, volumes, networks, databases, owners, and clients before changing it. Do not assume it is unused or remove it. PostgreSQL must be deployed separately; MariaDB cannot directly host this PostgreSQL database.
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
- What is the MariaDB container used for?
- Which migration method meets the acceptable downtime?
- How long to retain the old frozen cluster before destructive cleanup?
