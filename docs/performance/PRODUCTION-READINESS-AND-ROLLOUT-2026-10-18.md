# Indexed equipment rankings: production-readiness review and rollout

Status: **HOLD — plan approved for development, NOT authorized for production migration or feature activation**. Last verified production Alembic revision: `0012_manual_verify_api`; branch scratch head: `0013_indexed_equipment_rankings`.

## Verified evidence

- Isolated PostgreSQL 16 migrated 0001–0013. Consistent read-only production snapshot of 10,000 soldiers copied 953,680 raw weapon and 444,932 raw vehicle records. Backfill produced 953,680 weapon and 363,542 canonical vehicle records in 249.69 seconds.
- Bidirectional full-record comparison: 1,317,222 derived records, zero mismatches; 28 weapon/vehicle metric ranking cohorts zero mismatches; 14.62-second comparison runtime. Coverage: weapon IDs 5/6 and vehicle family IDs 1/2/41/62, all/PC, kills/KPM/accuracy where applicable.
- Scratch transactional stress: intentional rollback restored raw and derived values; 96 refresh transactions over eight threads succeeded; temporary website-style active/inactive exclusions agreed on eligible soldier counts.
- Full real persistence handler tests in scratch with derived writes enabled: weapon and vehicle successful collections, invalid lease rejection, raw+derived updates, event ledger, job finalization. Transactions rolled back. Two concurrent same-soldier refreshes serialized with an explicit `SELECT soldiers FOR UPDATE` lock in the test.

## Release-blocking gaps and risks

1. **Same-soldier serialization is not proven for the actual collector path.** Each resource handler locks its own `collection_jobs` row `FOR UPDATE`; weapon and vehicle jobs are different rows. The stress test adds a soldier-row lock that the production handler does not currently take. Before activation, introduce and test a common per-soldier transaction lock shared by both handlers and backfill (or another proven equivalent). Test opposing weapon/vehicle order, same-resource lease fencing, deadlock/timeout behavior, and updates racing backfill. Never assume the test's explicit lock is already present in production.
2. **Backfill can race live updates.** `process_window` deletes and reinserts derived records in windows, without a shared lock with collector refresh. Implement a coordinated backfill protocol (shared per-soldier locking or quiesced collector phase), verify resumed windows and post-backfill catch-up, and quantify lock impact.
3. **Actual website semantics not certified.** The 10K comparison uses the same family mapping helper on both sides, so it is not fully independent of the real website SQL. The website-managed `player_exclusions` table is not present in scratch; the temporary-table test is not an end-to-end API test. Independently compare website's actual SQL, active exclusions, missing/null scores, zero-only vehicle placeholders, all platforms, ties, rank/position, top_pct/divisions, search and pagination, top 10/50. Preserve legacy path for anything not proved equivalent.
4. **Fast path not implemented/benchmarked end to end.** Validate actual bounded index scans (`EXPLAIN (ANALYZE, BUFFERS)` on scratch), cohort population metadata and percentile semantics without full scans in hot path. Indexes alone do not prove a fast website request. Measure latency and DB load under representative concurrent HTTP requests.
5. **Operational scale differs.** 10K soldiers are a sample, not the entire production cohort. Benchmark full-data backfill duration, WAL/replication lag, disk space, vacuum impact and long-running read snapshots before scheduling any production change. Avoid keeping a production read-only snapshot open through scratch backfill. Validate database backups and replica health.
6. **Docs need final refresh.** `BACKFILL-OPERATIONS.md` and early implementation checkpoints describe older, incomplete test status. Update to current truth while preserving history, then make schema docs and live introspection agree.

## Proposed staged rollout (requires operator approval at the production gate)

A. Implement shared collector/backfill serialization and actual website SQL parity tests; add CI scratch tests. Do not modify production.

B. Build feature-flagged API indexed Top 10 for weapons (kills, KPM, accuracy) and vehicles (kills, KPM). Legacy rankings, search, pagination and divisions remain fallback. Benchmark on scratch; verify exact output and exclusions.

C. Stage a full production-sized isolated database rehearsal, including representative concurrent writes, WAL/disk/load monitoring, fail/rollback drills and read-only snapshot discipline. Establish go/no-go thresholds and an operator runbook.

D. **Separate production approval required:** verify backups and replicas; migrate production to 0013 with derived writes and reads OFF; verify migration and monitor replication. Schema rollback may require dropping derived tables; prefer disabling flags rather than destructive downgrade.

E. Coordinate backfill with live collectors using verified locking/catch-up; run bounded resumable batches with progress, errors, replica lag and WAL alerts. Re-run live parity against legacy output before enabling reads.

F. Enable derived collector writes, verify freshness and consistency; canary indexed API for one internal/admin audience, then progressively widen only after correctness and latency targets pass. Keep immediate kill switches for both write/read flags and legacy query fallback.

G. Monitor post-cutover: request p50/p95/p99, DB CPU/IO, query plans, replica lag, deadlocks, collector throughput, backfill/freshness drift, ranking parity. On anomaly, disable indexed API reads first; preserve original raw tables and legacy website queries. Investigate before any schema rollback.

## Explicit non-actions

No production migration, backfill, collector flag change, website deployment, service restart, or modification of the dirty `/opt/bf4ps-website` worktree is authorized by this planning review.
