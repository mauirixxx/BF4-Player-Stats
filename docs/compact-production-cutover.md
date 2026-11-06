# Compact ranking production cutover and operations

Status as of 2026-11-05: **four compact publishers active; legacy reader retired; compact retention performance investigation ongoing**. Earlier dated rollout notes below are historical.

## Architecture and deployed state

The reader uses full-cohort, format-2 compact generations, not top-500 rankings. Alembic production head is `0023_compact_exclusion_guard` on MAK-DB-02, verified during deployment. Compact publication pointers are in `equipment_rank_compact_published`; payloads are in `equipment_rank_compact_blocks`; metadata is in `equipment_rank_generations`. The website uses `rank_read_path_compact.py`, `bf4ps/compact_rank_codec.py`, and `bf4ps/compact_exclusions.py`. All are committed to GitHub main.

On tcou, the systemd drop-in `/etc/systemd/system/bf4ps-leaderboard-api.service.d/compact-rank-reads.conf` sets `BF4PS_COMPACT_RANK_READS=1`. The retired `BF4PS_PRECOMPUTED_RANK_READS` path has been removed. The fallback after compact ranking is live calculation, not legacy snapshots. The website's existing read-only database role `bf4ps_stage9c_d2` has SELECT on compact published, blocks, and lookup; no write grants were added.

## Verified production behavior

- Compact module imports successfully from the deployed website API directory.
- Direct compact read for PC weapon 6 kills returned population 208,277 and 10 rows.
- Live leaderboard HTTP first-page response: 200, ~18.6 ms; page 2: 200, ~12 ms.
- Division filter: 200, ~718 ms; player search: 200, ~629 ms; vehicle first page: 200, ~14 ms.
- Leaderboard service active with zero unexpected restarts in the cutover check.
- These are bounded smoke checks, not proof that every scope uses compact data.

## Rollback

Disable `BF4PS_COMPACT_RANK_READS` in the systemd drop-in, run `systemctl daemon-reload`, and restart `bf4ps-leaderboard-api.service`. The old reader has been removed; keep the schema intact. Previous leaderboard API backup on tcou: `/opt/bf4ps-website/api/leaderboard_api.py.precompact-20261103`.

## Remaining production gates

1. Verify that a production compact writer is running and publishing on a recurring schedule; do not confuse the legacy distributed-ranking worker monitor with compact publication health.
2. Measure compact published scope coverage, freshness, format-2 row counts, and fallback frequency.
3. Verify generation retention and cleanup, multi-hour replication/WAL behavior, and publication lease fencing.
4. Update `admin-ranking.html` and the authenticated `/ranking-status` endpoint to display **separate** compact publication and legacy queue metrics. No misleading “healthy” indicator when writer heartbeats are stale.
5. Recheck deep pagination, vehicle-family parity, search, and divisions on representative production scopes.

## Safe operations

Do not automatically enable broad writer jobs or delete generations based solely on reader activation. The reader is already live and independent of publication scheduling. Keep the direct live-calculation fallback; the legacy reader has been retired.

## Admin ranking monitor update (2026-11-03)

The production authenticated `/bf4ps-admin-api/ranking-status` response now includes `compact` aggregates (published scopes, format-2 scopes, published rows, scopes completed within 72 hours, newest completion) and `compact_recent` (up to 12 published generations). These are displayed above the **separately labeled legacy distributed ranking queue** on `/admin-ranking.html`. The admin DB role `bf4ps_admin_moderation` received SELECT-only access to `equipment_rank_compact_published` and `equipment_rank_generations`; no DML grants were added. The private API service restarted successfully and still rejects unauthenticated ranking-status requests with HTTP 401; the public HTML returned HTTP 200.

Initial direct database check found **15 published compact scopes**. This is limited coverage; do not mistake reader activation for continuous, full-fleet compact publication. Writer scheduling and retention are not yet confirmed. The updated page intentionally does not claim writer health from legacy worker heartbeats.


## Verified production update — 2026-11-04

The historical remaining-gates section above describes the initial reader-only cutover,
not the current deployment. Production now runs two continuous, parity-partitioned
compact ranking builders: MAK-01 handles odd equipment IDs and MAK-02 handles
even equipment IDs, for both weapons and vehicles across all platforms and metrics.
Both use the same code and a configurable `BF4PS_COMPACT_SCOPE_PARITY` setting.
The application-defined global capacity is 2. The WAL replay gate and fenced
claims remain active. See [compact-two-worker-parity.md](compact-two-worker-parity.md)
for configuration, validation and rollback.

The authenticated admin ranking monitor now reports scope publication coverage
against the database's ranking job inventory (2,624 scopes at the Nov 4 check),
format-2 coverage, rolling 24-hour publication count, published ranking rows,
two available build slots and active database claims. A claim is not a worker
heartbeat; host services and logs must be checked separately. Snapshot counts
are continuously changing and should not be treated as immutable release numbers.

The public soldier search at `/bf4ps-api/global-soldier-search` had a reproducible
HTTP 503 after the 5-second database statement timeout for `wart`.
The deployed `website/api/global_soldier_search.py` now builds a bounded set
of matching IDs using trigram-indexed current and historical names, then
enriches the resulting identities with stats and profile information.
Persona-ID search uses exact numeric identity matching. The public endpoint
returned HTTP 200 in 2.64 seconds for `wart`, the local endpoint returned
HTTP 200 in 0.47 seconds for `mauirixxx`, and a two-character search
returned HTTP 200 in 4.12 seconds. Search accepts 2–80 characters; broad
two-character queries can remain comparatively slow.

Outstanding acceptance work: confirm first full compact scope sweep and
refresh behavior, retention over multiple cycles, extended HA/failover and
replica-WAL monitoring, deep pagination/tie/division parity across all metrics,
and a clean-checkout deploy/build verification. Do not call the entire project
feature-complete on the strength of these targeted smoke checks alone.


## Four-shard publisher and retention update — 2026-11-05 UTC

The earlier two-worker odd/even deployment is historical. Current production compact
publishers run on MAK-01, MAK-02, MAK-03, and MAK-04, with
`BF4PS_COMPACT_SHARD_COUNT=4` and respective shard indices 0–3. Work is
partitioned by equipment `item_id % shard_count`, retaining the 15-second
scope refresh setting, claim fencing, capacity controls and replication/WAL
gate. Production `equipment_rank_capacity.max_active_builds` was changed
from 2 to 4. Expanding to more workers requires a coordinated stop,
repartition and restart, not an isolated shard-count edit.

On MAK-01, the bounded retention service now runs every minute, deleting
at most 20 eligible obsolete generations per invocation while preserving
the two newest generations per scope, published pointers and legacy-backed
generations. Two initial runs each deleted 20 generations successfully.
Theoretical capacity is 1,200 deletions/hour; sustained throughput and
stable storage growth have not yet been established. PostgreSQL generally
reuses vacuumed space rather than shrinking physical files immediately.

The live ranking monitor is deployed from
`/var/www/bf4playerstats.com/admin-ranking.html`. Ten visual worker slots
are MAK-01–MAK-05, HNL-01–HNL-03, KAH-01 and RNT-01. Reserved slots do
not imply an installed publisher. The UI uses the existing worker heartbeat
and active-claim API; compact publication node attribution and resettable
per-node run counters are not implemented. Do not infer node ownership
of historical generations from the current claims.

At a point-in-time check on MAK-DB-02, the compact blocks table occupied
approximately 60 GB and the database approximately 196 GB; all three
streaming replicas showed minimal replay backlog. Continue checking
retention, vacuum and growth before expanding beyond four workers.

## Production reconciliation — 2026-11-05 UTC

This section supersedes earlier reader, writer and retention status statements. The website uses the compact reader first, falling back directly to live calculation if compact is ineligible (including a 72-hour age limit, version or exclusion mismatch). The hourly legacy reader and workers have been retired from the active website and GitHub main.

Four continuous compact publisher services run on MAK-01–04, shard indices 0–3, with claim fencing, WAL gating and a 15-second scope refresh setting. The compact publisher services were restarted and verified active after the legacy cleanup. The leaderboard weapon and vehicle HTTP smoke checks returned 200.

Following a VMware snapshot checkpoint, a single committed transaction on MAK-DB-02 deleted 2,624 legacy publication pointers and truncated legacy ranking rows. Both legacy tables and their indexes remain in the schema for compatibility. The shared generations and compact published pointers (2,624 at verification), blocks and lookup were preserved. The database dropped from approximately 212 GB to 115 GB, reclaiming about 97 GB; all three replicas showed zero replay lag immediately afterward. Production Alembic remains `0023_compact_exclusion_guard`; no migrations or collector upgrades were performed.

Compact retention on MAK-01 uses `cleanup_compact_production.py`, preserving two newest generations per scope and deleting up to 20 obsolete generations per invocation. Deletes cascade into the compact blocks and lookup. Repeated multi-minute transactions were observed holding the shared capacity lock and blocking publishers. The minutely compact-retention timer was **stopped again** pending investigation; the running invocation had not yet completed at last verification. Publishers remained active. The separate legacy-generation GC timer was restarted; recheck its status before changing it. Test smaller batches and lock duration before restoring minutely retention. Historical earlier sections are retained as dated records, not current instructions.

## 2026-11-05: Alembic 0024 ranking publisher compatibility incident

Production was upgraded to `0024_profile_lookup_idx` for the homepage profile lookup index. The additive migration changes only `public.profile_soldiers` indexing, but the compact ranking publisher contained exact-revision guards for `0023_compact_exclusion_guard` in `run_compact_rank_scheduler.py`, `run_one_compact_scope.py`, and `build_compact_rank.py`. Consequently, ranking scopes failed with `expected migration 0023, got 0024_profile_lookup_idx`; the ranking watchdog reported due scopes with no active publication. The publisher code was updated to accept both revisions and to retain format-2 exclusion fingerprint publication on 0024. Four publisher hosts (MAK-01 through MAK-04) received the runtime patch. Production logs subsequently confirmed successful publications on MAK-01, MAK-02, MAK-03, and MAK-04; MAK-01/02 had zero systemd restarts when checked. Intermittent WAL-gate refusals on MAK-02 were observed, followed by successful publications; these are separate from the revision mismatch. Replication backlog subsequently drained to zero per operator observation.

**Deployment rule:** A schema migration rollout must audit all schema-revision guards in active publishers, builders, schedulers, collectors, and other related services, not just distribute the migration files. Verify successful publication on every publisher shard and inspect watchdog status before calling the rollout complete. Do not roll back the search index or bypass the WAL gate to resolve this compatibility issue. This section supersedes the historical statement above that production remains at 0023.
