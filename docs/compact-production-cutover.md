# Compact ranking production cutover and operations

Status as of 2026-11-03: **website compact reader activated on tcou; full-scope publication/refresh and retention remain to be verified**.

## Architecture and deployed state

The reader uses full-cohort, format-2 compact generations, not top-500 rankings. Alembic production head is `0023_compact_exclusion_guard` on MAK-DB-02, verified during deployment. Compact publication pointers are in `equipment_rank_compact_published`; payloads are in `equipment_rank_compact_blocks`; metadata is in `equipment_rank_generations`. The website uses `rank_read_path_compact.py`, `bf4ps/compact_rank_codec.py`, and `bf4ps/compact_exclusions.py`. All are committed to GitHub main.

On tcou, the systemd drop-in `/etc/systemd/system/bf4ps-leaderboard-api.service.d/compact-rank-reads.conf` sets `BF4PS_COMPACT_RANK_READS=1`. The existing `BF4PS_PRECOMPUTED_RANK_READS=1` remains as a fallback, followed by the legacy query path. The website's existing read-only database role `bf4ps_stage9c_d2` has SELECT on compact published, blocks, and lookup; no write grants were added.

## Verified production behavior

- Compact module imports successfully from the deployed website API directory.
- Direct compact read for PC weapon 6 kills returned population 208,277 and 10 rows.
- Live leaderboard HTTP first-page response: 200, ~18.6 ms; page 2: 200, ~12 ms.
- Division filter: 200, ~718 ms; player search: 200, ~629 ms; vehicle first page: 200, ~14 ms.
- Leaderboard service active with zero unexpected restarts in the cutover check.
- These are bounded smoke checks, not proof that every scope uses compact data.

## Rollback

Disable `BF4PS_COMPACT_RANK_READS` in the systemd drop-in, run `systemctl daemon-reload`, and restart `bf4ps-leaderboard-api.service`. Leave the old reader and schema in place. Previous leaderboard API backup on tcou: `/opt/bf4ps-website/api/leaderboard_api.py.precompact-20261103`.

## Remaining production gates

1. Verify that a production compact writer is running and publishing on a recurring schedule; do not confuse the legacy distributed-ranking worker monitor with compact publication health.
2. Measure compact published scope coverage, freshness, format-2 row counts, and fallback frequency.
3. Verify generation retention and cleanup, multi-hour replication/WAL behavior, and publication lease fencing.
4. Update `admin-ranking.html` and the authenticated `/ranking-status` endpoint to display **separate** compact publication and legacy queue metrics. No misleading “healthy” indicator when writer heartbeats are stale.
5. Recheck deep pagination, vehicle-family parity, search, and divisions on representative production scopes.

## Safe operations

Do not automatically enable broad writer jobs or delete generations based solely on reader activation. The reader is already live and independent of publication scheduling. Keep the existing legacy fallback until compact coverage and retention are proven.

## Admin ranking monitor update (2026-11-03)

The production authenticated `/bf4ps-admin-api/ranking-status` response now includes `compact` aggregates (published scopes, format-2 scopes, published rows, scopes completed within 72 hours, newest completion) and `compact_recent` (up to 12 published generations). These are displayed above the **separately labeled legacy distributed ranking queue** on `/admin-ranking.html`. The admin DB role `bf4ps_admin_moderation` received SELECT-only access to `equipment_rank_compact_published` and `equipment_rank_generations`; no DML grants were added. The private API service restarted successfully and still rejects unauthenticated ranking-status requests with HTTP 401; the public HTML returned HTTP 200.

Initial direct database check found **15 published compact scopes**. This is limited coverage; do not mistake reader activation for continuous, full-fleet compact publication. Writer scheduling and retention are not yet confirmed. The updated page intentionally does not claim writer health from legacy worker heartbeats.
