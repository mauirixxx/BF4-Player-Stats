# Distributed equipment ranking workers — design v0.1 (2026-10-21)

Status: DESIGN ONLY; not deployed. This document is the implementation reference. Verify `database-schema.md`, `operational-schema.md`, and live PostgreSQL catalog before writing migrations or database access code.

## Goals
- Support any number of registered nodes, with no node count or fixed hostname assumptions.
- Start with two nodes; bound actual simultaneous database-heavy builds by a configurable, centrally enforced concurrency budget, initially 2.
- Build all populated equipment scopes (kind, item, platform, metric), including weapon/gadgets and vehicles, across ALL/PC/PS4/Xbox One; refresh popular and stale scopes without starving unpopular ones.
- Preserve published immutable generations, website read guards, live fallback, exclusion policy, and existing rate/traffic budgets.
- Safe under node loss, transaction retries, lease expiry, competing claims, and primary DB failover.

## Existing implementation (verified on mak-01)
`player-collector/hourly_runner.py` holds PostgreSQL advisory lock (640041,170017) across entire batch. It currently selects top ten vehicles and top ten weapons, ALL-platform only; skips published generations younger than 3300s; limits to 50 jobs/1740s by default. `build_rank_hourly.py` computes immutable rows and swaps the publication pointer in a separate transaction. The observed run completed 45 builds in 489.1s, with zero failures. The existing runner MUST remain the production path until explicit cutover.

## Coordination schema (proposed, not yet migrated)
1. `equipment_rank_jobs`: unique (kind,item_id,platform,metric); fields include next_due_at, priority, last_success_at, last_error, attempts, state, claimed_by, lease_expires_at, claim_token UUID, claim_epoch bigint, updated_at, and desired_scope_version.
2. `equipment_rank_workers`: worker_id UUID primary key, hostname/site (informational only), heartbeat_at, started_at, enabled, version; no hardcoded fleet list.
3. `equipment_rank_capacity`: single policy row with max_active_builds, lease_seconds, heartbeat_seconds, max_attempts, retry/backoff settings. Capacity is configuration, not a fixed schema limit.
4. `equipment_rank_claims` (or equivalent immutable claim history) for audit, durations and failure classification. Confirm compatibility with existing rank generation and scope version tables before migration.

## Admission and claiming
- In one short transaction: select eligible due jobs with `FOR UPDATE SKIP LOCKED`; reserve one of the configured global slots atomically; assign owner, new token and monotonic epoch, set lease expiration; commit before expensive SQL.
- Slots are logical capacity permits, not worker identities. Enforce global cap transactionally, even if hundreds of nodes poll simultaneously. Do not rely on `COUNT(active)` without a serialized guard. Prefer row-locking the capacity policy row for admission and reclaim, or durable numbered permits under the policy.
- Claims are unique per scope. Each worker may claim a configurable number of jobs; default one active computation per process. A node may run multiple processes only if each is separately admitted.
- Lease heartbeats renew only for the current owner/token/epoch. Stale claims are reclaimed after expiration; workers must abort promptly when renewal fails.
- Protect against a lease expiring while SQL continues: PostgreSQL session-level cancellation or bounded statement timeout, and a *database-enforced fencing check* immediately before publishing. Publication must verify claim owner/token/epoch, unexpired lease, current scope version, exclusion constraints, and generation status inside the same transaction as the pointer swap. A stale worker cannot publish.
- Claims should not hold locks throughout expensive ranking computation. Generation insertion and ranking rows may be prepared before publication; failed/stale unpublished generations are garbage-collected later.
- Preserve exact-once publication semantics per scope/epoch, not exactly-once computation; duplicated compute after failures is acceptable but bounded.

## Scheduler
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

## Unresolved before implementation
- Verify exact live DDL for rank tables and exclusion checks; choose migrations and index strategy accordingly.
- Verify whether scope versions increment per collector update and how often; prevent high-churn scopes from perpetual invalidation.
- Measure PostgreSQL under a running build; host idle snapshot alone is insufficient.
- Confirm garbage collection for unpublished generations and historical generation retention.
- Confirm deployed production ranking builder matches repository before cutover.
