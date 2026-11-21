# BF4PS production PostgreSQL role names and retired database fleet

Status: operational reference, 2026-11-20/21 UTC. **Do not rename roles or delete database clusters merely because names look historical.**

## Legacy role `bf4_playerstats_test_migrator` — ACTIVE PRODUCTION

Despite the misleading word `test`, this PostgreSQL login is actively used for BF4PS production work on the standalone primary `bf4ps-db` (`192.168.10.66`). It is **not** an expendable test account.

Live `pg_stat_activity` inspection showed connections from `192.168.10.70`, `.71`, `.73`, and `.74`, including writes to `soldiers` and leaderboard ranking calculations with window functions. Collector environment files on `mak-01` through `mak-04` contain this username; other collector hosts and scheduled jobs must be audited before any credential change. The repository also references the role in historical provisioning and GRANT scripts. No role rename was performed.

The related `bf4ps_stage9c_d2` account is also production-active, serving population/collection coverage queries. `bf4ps_platoon_collector` is production-active for platoon discovery. Names such as `stage9c` and `test_migrator` are **legacy labels, not evidence of abandoned workloads**.

**Operator rule:** Leave these logins unchanged unless there is a separately approved, fleet-wide authentication migration. Do not terminate their sessions, revoke privileges, rotate credentials, or run historical provisioning scripts as a naming cleanup. If a rename is ever needed, inventory all active service configurations, container environments, cron/systemd timers, API services, stored secrets and source-code references, and stage a rollback.

## Database topology after November 2026 migration

Current authoritative BF4PS primary: `bf4ps-db`, PostgreSQL 16, data directory `/fast/pgdata` on the mirrored SSD ZFS pool. The pre-SSD-move HDD copy at `/tank/pgdata` is preserved for rollback. Current production Alembic revision was verified as `0025_compact_lookup_fk_idx`; proposed `0026` is not deployed.

Legacy independent PostgreSQL cluster (not the live BF4PS primary):
- `mak-db-02`: old writable primary; `bf4_playerstats` approximately 460 GB; actively streaming to three legacy replicas, no application connections to `bf4_playerstats` during the check.
- `mak-db-01`: old streaming standby; same approximately 460 GB BF4PS database; no application connections.
- `rnt-db-01`: old streaming standby; same approximately 460 GB BF4PS database; no application connections.
- `hnl-db-01`: old streaming standby; same approximately 460 GB BF4PS database; no application connections; critically low disk space (~3.8 GB free at inspection).
- `kah-db-01`: PostgreSQL 16 cluster **down,in recovery** at inspection, not an active streaming replica; only ~51 GB used on its 128 GB filesystem. Do not assume it has a complete 460 GB copy.

The old primary also hosts other databases, including `bf4_serverwatcher`, `bf4_playertracker`, `bf4ps_discord`, and scratch databases. Preserve these until independently inventoried and verified unused or migrated.

**Deletion guard:** No old BF4PS database has been dropped as part of this documentation. Do not run `DROP DATABASE` on standbys (they are read-only), and do not delete the old primary's BF4PS database without first verifying independent backups, service endpoint inventories, replica topology, recovery requirements, and explicit approval of the irreversible deletion. A drop on the old primary propagates to connected streaming standbys, and retaining the old cluster temporarily provides a rollback safety net. The offline KAH host requires separate treatment.

For schema-specific operations, consult `docs/database-schema-reference.md` and current Alembic migrations first.
