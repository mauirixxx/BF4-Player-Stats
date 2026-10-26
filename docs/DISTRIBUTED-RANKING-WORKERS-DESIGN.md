# Distributed equipment ranking workers — design v0.1 (2026-10-21)

Status (2026-10-21): PRODUCTION MIGRATED, WORKERS PAUSED FOR REPLICATION BACKPRESSURE. PostgreSQL bf4_playerstats migrated to 0018; legacy hourly timer disabled; distributed worker systemd services disabled/inactive on mak-01 and rnt-01 pending WAL/network throughput investigation; centrally enforced global capacity=1. Scratch PostgreSQL 0018 previously validated on rnt-01. This document is the implementation reference. Verify `database-schema.md`, `operational-schema.md`, and live PostgreSQL catalog before writing migrations or database access code.

## Goals
- Support any number of registered nodes with no fixed hostname assumptions; initial centrally enforced concurrent build capacity is 1, with a later controlled benchmark at 2 after replication health is confirmed.
- Build all populated equipment scopes (kind, item, platform, metric), including weapon/gadgets and vehicles, across ALL/PC/PS4/Xbox One; refresh popular and stale scopes without starving unpopular ones.
- Preserve published immutable generations, website read guards, live fallback, exclusion policy, and existing rate/traffic budgets.
- Safe under node loss, transaction retries, lease expiry, competing claims, and primary DB failover.

## Existing implementation (verified on mak-01)
The legacy `hourly_runner.py` holds PostgreSQL advisory lock (640041,170017) across its batch. On 2026-10-21 the production staged runner selects top ten weapons (kills/KPM/accuracy), top ten vehicles (kills/KPM), plus UCAV vehicle_id=10, across ALL/PC/PS4/Xbox One. It skips generations younger than 3300s and limits to 200 jobs/1740s. A measured hourly run completed 47 jobs in 503.4s without failures. The legacy runner was retired from scheduled production during the 2026-10-21 drain/migrate/cutover sequence below.

## Coordination schema (implemented in Alembic 0018; scratch only as of 2026-10-21)
1. `equipment_rank_jobs`: primary key (kind,item_id,platform,metric); next_due_at, last_success_at, last_error, attempts, claimed_by, lease_expires_at, claim_token UUID, claim_epoch bigint, updated_at. No separate priority/state/desired_scope_version columns in 0018.
2. `equipment_rank_workers`: worker_id UUID primary key, hostname/site, heartbeat_at, started_at. No fixed fleet list.
3. `equipment_rank_capacity`: singleton id=1, max_active_builds=1 and lease_seconds=180 by default. Capacity-row `FOR UPDATE` serializes admission; active lease count is checked under that lock.
4. Claim history is not implemented as a separate table. Successful generation publications remain recorded in immutable generation tables.

## Admission and claiming
- In one short transaction: select eligible due jobs with `FOR UPDATE SKIP LOCKED`; reserve one of the configured global slots atomically; assign owner, new token and monotonic epoch, set lease expiration; commit before expensive SQL.
- Slots are logical capacity permits, not worker identities. Enforce global cap transactionally, even if hundreds of nodes poll simultaneously. Do not rely on `COUNT(active)` without a serialized guard. Prefer row-locking the capacity policy row for admission and reclaim, or durable numbered permits under the policy.
- Claims are unique per scope. Each worker may claim a configurable number of jobs; default one active computation per process. A node may run multiple processes only if each is separately admitted.
- Lease heartbeats renew only for the current owner/token/epoch. Stale claims are reclaimed after expiration; workers must abort promptly when renewal fails.
- Protect against a lease expiring while SQL continues: PostgreSQL session-level cancellation or bounded statement timeout, and a *database-enforced fencing check* immediately before publishing. Publication must verify claim owner/token/epoch, unexpired lease, current scope version, exclusion constraints, and generation status inside the same transaction as the pointer swap. A stale worker cannot publish.
- Claims should not hold locks throughout expensive ranking computation. Generation insertion and ranking rows may be prepared before publication; failed/stale unpublished generations are garbage-collected later.
- Preserve exact-once publication semantics per scope/epoch, not exactly-once computation; duplicated compute after failures is acceptable but bounded.

## Scheduler
- Current code orders due jobs: scopes overdue by at least 24h (oldest first), then ALL-platform jobs, UCAV vehicle_id=10, descending equipment population, and due timestamp. This is a population-based proxy, not an exact top-ten kills policy; validate realistic queue ordering before production cutover.
- Site affinity (2026-10-21): all workers registered with `site='mak'` take precedence; non-mak workers decline new claims while any mak worker has a heartbeat younger than 30 seconds. After mak heartbeats expire, remote workers may claim jobs automatically. This is a standby preference, not a fixed hostname list. Global concurrency still applies.
- Worker refresh intervals: `BF4PS_RANK_REFRESH_ALL_SECONDS` and `BF4PS_RANK_REFRESH_PLATFORM_SECONDS`, default 3600, accepted range 300–10800 seconds. Retries use bounded exponential backoff.
- Discover scope population from canonical catalog and existing `equipment_rank_scope_versions` and `equipment_population`; no hardcoded item IDs.
- Persist due timestamps. First-time missing scopes outrank routine refresh, but use bounded aging/fairness to prevent permanent starvation.
- Per-scope freshness target is configurable by popularity and demand; first backfill and steady-state are different policies.
- Jobs are eligible only when catalog population > 0, metrics supported, and exclusion/version policy can be enforced. Unsupported combinations are not silently queued.
- On success, calculate next_due_at. On transient error, exponential bounded retry. Terminal schema/policy errors require operator attention. Never tight-loop failures.

## Database safety and rollout
1. Baseline on one worker: wall time, p50/p95 build duration, DB CPU/load, read/write IOPS and latency, WAL bytes/sec, replication lag, website API p50/p95, lock waits, temp file usage, active sessions.
2. Migration and queue bootstrap are additive and idempotent; schema review and scratch concurrency tests first.
3. Prove race: two claims, lease expiry, worker crash, delayed stale publisher, DB failover, scope-version change, exclusion during compute, and rollback.
4. Deploy workers on two distinct nodes with global capacity=1 first; confirm identical result and failover. Raise capacity to 2 for controlled benchmark; keep the existing runner disabled only after replacement proves correct.
5. Stop or reduce admission if replication lag, DB load, website latency, WAL pressure or error thresholds breach configurable limits. No automatic unbounded scaling.
6. Scale nodes freely thereafter; capacity remains an independent runtime policy. Include kill switch capacity=0 (no new claims) and graceful drain.
7. Rollback to legacy runner requires draining new claims, confirming no active publishers, and avoiding simultaneous legacy/new execution. Existing published generations remain readable.

## Verified test evidence and production cutover gates
- On rnt-01 isolated PostgreSQL `bf4ps_ranking_scratch`: migrated 0017 to 0018; competing claim/capacity=1, expired lease reclaim, stale-token rejection test PASS; six discovered jobs; actual fenced ranking builds published generations (96,674-row ALL and 64,330-row PC samples).
- Before cutover, systemd worker services were staged and verified on mak-01 and rnt-01; the legacy hourly timer was enabled. See activation evidence below for current state.
- Cutover sequence: confirm production replication health and schema; validate realistic queue ordering; verify deployed builder/image parity and environment; drain/disable legacy hourly timer and ensure no running legacy builder; apply production Alembic 0018; bootstrap queue and set global cap=1; enable workers one node at a time; verify published generations, website freshness and replica lag. Rollback: disable/drain distributed services, verify no active claims/publishers, then re-enable legacy timer. Never overlap legacy and distributed publishers.

## Production activation evidence (2026-10-21)
- `mak-01`: stopped and disabled `bf4ps-hourly-rank-builder.timer` while service was inactive; migrated production from Alembic 0017 to 0018; discovered 2,624 queue jobs; enabled `bf4ps-distributed-rank-worker.service`.
- `rnt-01`: enabled `bf4ps-distributed-rank-worker.service` against the same production database. Both workers registered successfully; capacity=1 permits only one active job across both.
- First fenced production publication: UCAV vehicle_id=10, ALL kills, generation 842, 144,964 rows, 7.24s; followed by ALL KPM generation 843, 144,965 rows, 7.31s. Both marked completed successfully. Subsequent weapon job claimed.
- Primary PostgreSQL replication checked as superuser immediately before cutover: four asynchronous replicas streaming, each 344 bytes behind at observation time. Application role masks pg_stat_replication detail.
- Rollback remains available: stop/disable both distributed services, wait for active leases/publishers to drain, then re-enable the legacy timer; the legacy builder must not run concurrently with distributed publishers and its schema-0017 guard must be adjusted or migration reverted before using it on schema 0018.

## Live admin ranking monitor (2026-10-21)
- `/admin-console.html` uses a content-sized left navigation column, with sections for Collection Overview, Player Moderation, Database & Account, and a link to the separate ranking monitor.
- `/admin-ranking.html` refreshes every five seconds; the same admin session protects `GET /bf4ps-admin-api/ranking-status`. The endpoint is read-only, sets a 2.5-second statement timeout, and returns queue totals, due/active/error counts, recent success counts, active claim owners, worker heartbeats, capacity, and latest successful scopes. The restricted role `bf4ps_admin_moderation` has SELECT only on the three ranking coordination tables.
- PostgreSQL replication is displayed through the narrowly scoped SECURITY DEFINER function `public.bf4ps_admin_replication_status()`, provisioned by `website/scripts/provision_rank_replication_monitor.sql`; only aggregate streaming/total counts and maximum replay lag bytes are exposed to the admin role.
- Authenticated production smoke test: HTTP 200, 2,624 jobs, one active lease, three registered worker rows, twelve recent successful scopes. Unauthenticated request returns HTTP 401.

## Backpressure incident / operational pause (2026-10-21)
- During initial 2,624-job backlog, the monitor detected up to ~26 GB WAL replay lag on remote replicas. Superuser inspection on primary mak-db-02 showed four streaming replicas: local mak replica caught up; remote hnl/kah replicas had ~24 GB unsent, rnt ~5 GB unsent. This is transmission backlog rather than slow SQL replay; remote WAN links are a bottleneck.
- Both distributed worker services were disabled/stopped; legacy hourly timer remains disabled to protect website latency and allow replicas to catch up. The rank data already published remains readable.
- Do not resume the full backfill until WAL generation is paced against actual remote replication bandwidth. Consider a configurable global admission budget/duty cycle, replica-lag circuit breaker, and a smaller priority-only set first. Site preference (`mak` first, remote standby) controls where ranking computation happens, but does not remove WAL replication traffic to remote database replicas.

## Remaining operational follow-ups
- Periodically re-verify live DDL and ranking exclusion behavior against the schema reference.
- Verify whether scope versions increment per collector update and how often; prevent high-churn scopes from perpetual invalidation.
- Measure PostgreSQL under a running build; host idle snapshot alone is insufficient.
- Confirm garbage collection for unpublished generations and historical generation retention.
- Confirm deployed production ranking builder matches repository before cutover.

## Replication-aware admission guard (2026-10-21)
- A controlled one-worker restart from zero backlog generated ~800 MB unsent WAN WAL after one ~145k-row ranking publication. The operator stopped the service immediately; all four replicas later caught up again. Do not run unguarded continuous ranking.
- Production queue admission (under the existing capacity-row lock) now fails closed unless all four expected replicas are streaming and maximum replay lag is <=128 MiB (configurable `BF4PS_RANK_MAX_REPLICA_LAG_BYTES`, range 1 MiB–1 GiB). This uses `public.bf4ps_rank_replication_admission_status()`, a SECURITY DEFINER aggregate with EXECUTE limited to the ranking-worker database role. Provision with the existing `website/scripts/provision_rank_replication_monitor.sql` on the writable primary. No direct `pg_monitor` privilege is granted.
- The initial duty cycle permits no more than one successful published ranking per five minutes, globally, based on last successful publication under the same admission lock. It is deliberately conservative; failed jobs may need an additional admission timestamp if they become common. A successful publication can temporarily exceed the lag threshold; the guard prevents subsequent claims, not mid-build WAL generation. Retain cap=1 and MAK site preference. Reassess using observed WAN drain rate and website latency before increasing throughput.

### Temporary MAK/RNT-only ranking admission (2026-10-21)
Physical replication still ships **all databases** to HNL/KAH; do not drop those slots or change BF4SW failover. Ranking admission now requires only `mak_db_01` and `rnt_db_01` to stream within 128 MiB replay lag. HNL/KAH lag does not block a new ranking **until** any physical slot retains more than 32 GiB of WAL, at which point ranking stops to protect the 128 GiB primary filesystem. This is a bounded temporary compromise, not unlimited permission to accumulate WAL. Monitor primary free space and all four slots; the five-minute global ranking duty cycle remains. The admission SQL function's return signature changes and must be dropped/recreated on the primary; it remains executable only by the worker DB role. Revisit a dedicated BF4PS PostgreSQL instance/cluster when convenient.

### Production continuous rolling refresh (2026-10-26)

Production `mak-01` runs the distributed rank worker continuously with `BF4PS_RANK_REFRESH_ALL_SECONDS=300` and `BF4PS_RANK_REFRESH_PLATFORM_SECONDS=300` injected into the Docker invocation. The live systemd unit is tracked at `player-collector/deploy/systemd/bf4ps-distributed-rank-worker.service`. The source code's default remains 172800 seconds (48 hours) if these environment overrides are omitted, so preserve them on every deployment. `refresh_interval()` enforces a 300-second minimum. A successful job reschedules itself for five minutes after completion; the worker immediately claims another eligible job. This is a continuously cycling rolling queue, not an atomic batch restart. On 2026-10-26 all 2,624 completed scopes were explicitly made due once to resume the first continuous pass, and the worker successfully claimed `vehicle 10 / all / kpm`. Capacity stays at one active builder; replication safety gate, lease fencing and error backoff remain enabled. The legacy `bf4ps-hourly-rank-builder.timer` must remain disabled. Watch DB WAL/replica lag and ranking throughput during sustained operation. The earlier design note describing a 3600-second default is superseded by this production deployment and the source's actual 172800-second fallback.

### 2026-10-26 — obsolete generation cleanup and storage pressure

User cancelled historical/improvement-over-time retention. Live production `equipment_rank_generations` contained 2,624 published, 874 retired and 1 failed generations, with metadata `row_count` sums of approximately 290.2M published and 109.3M retired rows. `equipment_rank_rows` occupied approximately 79 GiB including 46 GiB of indexes, making it the primary database space consumer. Do **not** delete published generations: they back live rankings. The existing `retired_snapshot_gc.py` safely removes retired generations older than two hours only if unreferenced by `equipment_rank_published`, with FK cascading rows. One retired generation (401, 94,566 rows) was deleted as a successful test. The production `bf4ps-rank-gc` service/timer on mak-01 was updated from 3 generations hourly to 5 generations every 5 minutes; the first scheduled run successfully removed generations 402–406. Deployed units are tracked in `player-collector/deploy/systemd/`. This is bounded cleanup, not wholesale retention deletion. Monitor the number of retired generations, WAL volume, replica lag, and disk free space. Ordinary DELETE/VACUUM reuses storage internally and **does not immediately shrink PostgreSQL relation files**. A separately planned, storage-budgeted online table/index compaction and a review of current snapshot row cardinality are still needed before claiming disk space reclaimed. Historical `detailed_stats_history` and other history-related tables have not been touched; evaluate their dependencies before removing them. No live published ranking generations were intentionally deleted.
