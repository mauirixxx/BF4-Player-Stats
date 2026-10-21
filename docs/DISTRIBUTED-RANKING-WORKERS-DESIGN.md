# Distributed equipment ranking workers — design v0.1 (2026-10-21)

Status (2026-10-21): IMPLEMENTED AND STAGED; scratch PostgreSQL 0018 migrated and validated on rnt-01, production still at 0017 with legacy hourly timer enabled. Distributed worker service units staged but disabled on mak-01 and rnt-01. This document is the implementation reference. Verify `database-schema.md`, `operational-schema.md`, and live PostgreSQL catalog before writing migrations or database access code.

## Goals
- Support any number of registered nodes with no fixed hostname assumptions; initial centrally enforced concurrent build capacity is 1, with a later controlled benchmark at 2 after replication health is confirmed.
- Build all populated equipment scopes (kind, item, platform, metric), including weapon/gadgets and vehicles, across ALL/PC/PS4/Xbox One; refresh popular and stale scopes without starving unpopular ones.
- Preserve published immutable generations, website read guards, live fallback, exclusion policy, and existing rate/traffic budgets.
- Safe under node loss, transaction retries, lease expiry, competing claims, and primary DB failover.

## Existing implementation (verified on mak-01)
The legacy `hourly_runner.py` holds PostgreSQL advisory lock (640041,170017) across its batch. On 2026-10-21 the production staged runner selects top ten weapons (kills/KPM/accuracy), top ten vehicles (kills/KPM), plus UCAV vehicle_id=10, across ALL/PC/PS4/Xbox One. It skips generations younger than 3300s and limits to 200 jobs/1740s. A measured hourly run completed 47 jobs in 503.4s without failures. The legacy runner MUST remain production until the explicit drain/migrate/cutover sequence below.

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
- Systemd `bf4ps-distributed-rank-worker.service` staged and verified on mak-01 and rnt-01, but disabled/inactive. The existing production hourly timer is still enabled.
- Cutover sequence: confirm production replication health and schema; validate realistic queue ordering; verify deployed builder/image parity and environment; drain/disable legacy hourly timer and ensure no running legacy builder; apply production Alembic 0018; bootstrap queue and set global cap=1; enable workers one node at a time; verify published generations, website freshness and replica lag. Rollback: disable/drain distributed services, verify no active claims/publishers, then re-enable legacy timer. Never overlap legacy and distributed publishers.

## Unresolved before production cutover
- Verify exact live DDL for rank tables and exclusion checks; choose migrations and index strategy accordingly.
- Verify whether scope versions increment per collector update and how often; prevent high-churn scopes from perpetual invalidation.
- Measure PostgreSQL under a running build; host idle snapshot alone is insufficient.
- Confirm garbage collection for unpublished generations and historical generation retention.
- Confirm deployed production ranking builder matches repository before cutover.
