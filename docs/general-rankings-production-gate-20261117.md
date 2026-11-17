# General ranking deployment gate — 2026-11-17 UTC

**Decision: NO-GO for production 0026 migration or general ranking writer activation.** A production replica is already down from disk exhaustion and other replicas have critically low free space. No production writes or service changes were performed during these checks.

## Scratch validation

- Real HTTP request with BF4PS_GENERAL_RANK_SNAPSHOT_READS=1 and temporarily absent kills/all publication pointer correctly returned legacy rank_source=live and population=560000. Original generation 9 publication pointer was restored in a finally block. Isolated RNT-01 scratch only.
- Measured three bounded retention invocations on RNT-01 scratch; all 56 published pointers intact:
  - obsolete generation 2: 0.365 sec, 78,798,120 bytes WAL interval.
  - obsolete generation 3: 0.002 sec, 138,464 bytes WAL interval.
  - obsolete generation 13: 0.001 sec, 160 bytes WAL interval.
- WAL interval measurements can include unrelated activity; generation sizes differ substantially. These three deletions are not proof of sustained 56-scope retention throughput. Deletion does not necessarily return disk space to filesystem; PostgreSQL VACUUM and reuse behavior must be considered.

## Production fleet read-only observations

| Host | Storage / PostgreSQL |
|---|---|
| MAK-DB-02 primary | Desktop Commander device offline for ~131 hours; no direct disk check possible. HNL-DB-01 reported active streaming from 192.168.10.78:5432 at 2026-11-17 21:10 UTC, so this does NOT prove primary database is down. |
| MAK-DB-01 | Root filesystem 491G total, 470G used, **0 available**, 100%; PostgreSQL 16/main **down,recovery**. Log at 2026-11-17 16:43:04 UTC: FATAL could not extend base/200111/981360.397, No space left on device during WAL redo; startup process exited and cluster shut down. |
| HNL-DB-01 | 540G root, 511G used, **6.3G available**, 99%; PostgreSQL 16/main online,recovery; Alembic 0025, replay timestamp near current at inspection. Streaming from primary confirmed. |
| RNT-DB-01 | 540G root, 515G used, **2.6G available**, 100% rounded; PostgreSQL 16/main online,recovery; Alembic 0025, replay timestamp near current at inspection. |
| KAH-DB-01 | 128G root, 51G used, 72G available; PostgreSQL 16/main down,recovery. systemd journal shows deliberate stop on 2026-10-22; no equivalent disk-full error observed. May be a stale or deliberately disabled replica; verify intended role before restart. |

PostgreSQL 16.15 on responding HNL/RNT replicas. Local socket unavailable on MAK-DB-01 and KAH-DB-01; this was corroborated by pg_lsclusters.

## Required immediate operational decisions

1. Restore headroom on production replicas, particularly MAK-DB-01, RNT-DB-01, and HNL-DB-01. Investigate growth sources, compact generation retention and existing WAL/TOAST before adding another ranking writer. **Do not delete PostgreSQL relation files, WAL files, or database contents manually.**
2. Confirm MAK-DB-02 primary free space and replication slots/status via an authorized path; Desktop Commander management agent is offline, but HNL streaming demonstrates PostgreSQL connectivity at inspection.
3. Determine whether MAK-DB-01 requires additional disk or safe rebuild after storage capacity is expanded; do not blindly restart a zero-space replica.
4. Verify intended status of KAH-DB-01; its 128G disk is much smaller than the other replica disks and likely insufficient for current full production data if intended as full replica. Do not assume it is usable.
5. Reassess actual primary/replica free space and WAL replay before applying 0026. Keep general snapshot writer and scheduler OFF.

## Source of truth

Read docs/database-schema-reference.md and current Alembic migrations before any schema-dependent action. The scratch tests are in website/tests/scratch_general_rank_missing_pointer_http.py and player-collector/tests/scratch_general_rank_retention_benchmark.py. All figures above are point-in-time measurements; repeat checks after capacity remediation.
