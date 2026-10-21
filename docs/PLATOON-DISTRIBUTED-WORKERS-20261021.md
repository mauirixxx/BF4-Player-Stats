# BF4PS distributed platoon/discovery workers — implementation contract

Status: implementation in progress; NOT deployed to multiple hosts.

## Verified production schema (2026-10-21)

- `platoons`: `platoon_id` bigint, `next_refresh_at` timestamptz, `last_success_at` timestamptz, `last_error` text.
- `platoon_requests`: `platoon_id` bigint PK, `status` pending/running/complete/failed, `attempts`, `next_attempt_at`, `last_attempt_at`, `last_error`.
- `platoon_soldier_discovery`: `soldier_id` bigint PK, `status` pending/running/complete/failed, `attempts`, `next_attempt_at`, `last_checked_at`, `linked_platoon_id`, `displayed_tag`, `last_error`.
- Existing mak-05 scheduler uses host-local flock, then SELECT and UPDATE in separate psql sessions; unsafe for multi-host concurrency.
- Production observed: 3,163 platoons; 71,883 pending discovery jobs; 267 failed platoon requests; 74 failed discovery jobs.

## Required invariant

No two workers may fetch/import the same platoon or discover the same soldier concurrently. Claims must be atomic in PostgreSQL, not file locks. Every claim has a random token, owner identity, expiry, and renewal or bounded maximum operation duration. Completion/failure must be conditional on ownership token; stale workers must not mutate job state. A stolen/expired claim must not overlap an in-flight HTTP fetch or import. Protect roster writes with an additional per-platoon database advisory lock or ownership verification immediately before import. On DB unavailability do not fetch.

## Deployment sequence

1. Add a dedicated claim table keyed by `(kind, subject_id)` and unique ownership tokens, expiry, indexes and grants. Confirm live grants/schema first. Keep existing worker running.
2. Implement atomic claim SQL for queued platoon requests, due known-platoon refreshes, and pending soldier discovery. Acquire/renew/release claims transactionally. Preserve admissions priority, bounded retries and 24-hour refresh interval. Reconcile old `running` rows from single-node implementation.
3. Integrate claim API into existing scripts without modifying Battlelog parser or roster import semantics. Avoid whole-roster failure from excluded soldier identities: admission should skip excluded identities, not disable DB guard.
4. Add process identity, per-node pacing and structured logs. Keep mak-05 only until single-worker canary passes.
5. Install on hnl-03 alongside existing BF4PS collector; first test simultaneous claims, stale recovery, and exclusion handling; verify distinct IDs and zero duplicate concurrent fetches.
6. Expand via same deployment package to other nodes after telemetry validates pacing, lock wait, claim expiry, success/failure and queue drain.

## Safety

Do not activate a second worker before all claim paths are atomic. Do not increase Battlelog request rate while concurrency changes are being validated. Do not reset the dirty mak-05 checkout; preserve four local commits and untracked backup files. DB endpoint `db.bf4statusbot.com`.
