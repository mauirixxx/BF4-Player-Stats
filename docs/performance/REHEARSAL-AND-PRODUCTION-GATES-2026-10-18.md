# Indexed rankings rehearsal evidence and production gates — 2026-10-18

Status: **HOLD — isolated rehearsal only; NO production migration or activation**.

## Observed isolated PG16 0013 snapshot

- 10,000 soldiers, 953,680 derived weapon metrics, 363,542 derived vehicle metrics; scratch DB size 545 MB. Scratch has a website-compatible `player_exclusions` table created solely for SQL testing.
- Actual website legacy `get_page` versus new indexed `query_top10`: 10/10 cohort checks matched population, ordered Top 10, kills/KPM/accuracy, rank, position, division. Weapon 5 and canonical vehicle 1, all/PC. One scratch-only active-exclusion transaction removed the leader; both paths agreed on new leader and population 4,574, then rolled back.
- EXPLAIN ANALYZE BUFFERS, warm-cache single executions, PC platform: weapon kills 0.446 ms; weapon KPM 0.474 ms; weapon accuracy 0.411 ms; vehicle kills 0.499 ms; vehicle KPM 0.496 ms. Each Top 10 query used its corresponding dedicated ix_*_top index-only scan; measured times exclude separate population count, HTTP, Python serialization, and network.
- Weapon 5 PC population count 6.772 ms, scanning 4,575 eligible records; **population count is not a bounded Top 10 fast path**. More efficient population metadata is a follow-on optimization.
- Earlier full scratch derived backfill: 249.69 s for 10K soldiers, 1,317,222 derived records, zero full-record mismatches. Shared soldier locks now present in branch code; scratch contention/timeout tests passed. No production-scale backfill, concurrent full collector-vs-backfill committed race, replica/WAL benchmark, or HTTP load test yet.

## Go/no-go criteria (must be checked, not assumed)

1. **Code/schema**: Confirm actual production Alembic revision, migration 0013 SQL, index definitions, schema reference, and lock ordering; run complete test suite and all scratch collision tests. No deployment from uncommitted tcou website files. Reconcile website feature branch with the exact intended deploy tree.
2. **Correctness**: Validate real website SQL against indexed SQL for all platforms, diverse weapon IDs and vehicle families (SUM/MAX), null/zero-only/ties, active/inactive exclusions, all five metrics, and legacy fallback search, pagination, divisions. Verify rank/position/top_pct and output shape. Ensure derived data freshness during collection.
3. **Capacity**: Obtain full-sized isolated copy with short-lived production read-only snapshot; measure migration, backfill throughput, WAL generated, replica lag, disk headroom, lock waits, CPU/IO, p50/p95/p99 under representative HTTP concurrency. No live Battlelog requests for rehearsal.
4. **Safety**: Verify tested recent backup and restoration path, all replicas healthy, maintenance/on-call contact, exact versions/commits, approved change window and abort thresholds. Capture current configuration and deployment manifests without exposing credentials.
5. **Approval**: Obtain explicit operator go-ahead for production schema migration as a separate step. Keep `BF4PS_RANKING_DERIVED_WRITES=0` and `BF4PS_INDEXED_EQUIPMENT_READS=0` through migration. Verify revision/replicas before controlled backfill and write activation. Reads must remain off until population/freshness/parity pass.

## Staged production runbook (NOT commands to execute yet)

- Preflight: collect baseline revision, replication lag, disk/WAL, API latency, collector health and snapshot of config; validate backup/restore and permissions. Confirm no pending long-running transactions or competing DDL.
- Gate 1 (explicit approval): migrate only the primary database to 0013 with both flags OFF. Check schema/indexes, database health and replica replay. Abort on migration errors or replica health deterioration.
- Gate 2: activate transactional derived maintenance only when compatible collector builds and shared soldier locking are deployed on every writer; coordinate resumable, single-runner backfill. Monitor lock waits and replica lag after each batch; pause on thresholds.
- Gate 3: run read-only legacy/indexed parity including exclusions and freshness, all platform/metric cases; test search/pagination legacy path and query budgets.
- Gate 4: deploy reviewed website build to a separate internal canary service with indexed reads ON there only. Monitor HTTP p50/p95/p99, 5xx, query load, replica lag, and ranking parity. Broaden traffic only after sign-off.
- Rollback: turn indexed reads OFF first and route back to legacy API; if collector/DB health suffers, pause backfill and disable derived writes on all collectors. Do not downgrade/drop derived schema automatically. Preserve raw tables, snapshots, logs and diagnostic evidence. Any destructive rollback requires separate authorization.

## Known blockers after this rehearsal

- Full-sized staging rehearsal and replication/WAL/load measurements absent.
- Website branch snapshots existing dirty tcou leaderboard edits; merge/deployment provenance needs review.
- Limited real SQL parity (10 cohorts plus one active exclusion); complete matrix and HTTP tests absent.
- Full collector-vs-backfill concurrent committed test and long-window locking benchmark absent.
- Population metadata still computed by separate cohort count; must measure at full scale.

Production untouched by this rehearsal. Scratch changes only: website-compatible exclusion table in isolated 10K DB. No website service restart or production flags changed.

## Additional isolated rehearsal — post-backfill verification

- Four committed 250-ID windows [1,1001) completed in 10.71 s with clean exit; resumable at 1001. Post-run counts verified unchanged: 953,680 derived weapon and 363,542 derived vehicle rows. Disk still reported 11 GB available (64% used).
- Scratch WAL LSN observed before batch `0/3C22FEC0` and after `0/44D1B390`: `pg_wal_lsn_diff` 145,667,280 bytes (~139 MiB). **This is an interval-wide WAL delta, not an isolated backfill-only attribution**. No replica exists on this standalone scratch container; replication lag not measured.
- Re-ran scratch lock-collision suite: rival lock acquisition refused, transaction rollback released lock, backfill timeout preserved baseline, opposite-resource refreshes completed, retry backfill succeeded. All PASS.
- Re-ran full real weapon and vehicle persistence-handler scratch tests including stale lease rejection, collection events/finalization and same-soldier serialization: PASS.
- Re-ran 96 concurrent refresh transactions across 8 workers, rolled back, plus exclusion parity: PASS (4.00 s).
- These concurrency suites **do not prove** a sustained committed collector-versus-backfill race on a full-size staging copy; preserve that release gate.
