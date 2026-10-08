# Stage 9C — shared watchdog lease and sticky abort (design v1)

Status: **DESIGN ONLY — no migration, activation, or live processes authorized**.

## Verified starting point

The documented schema and Alembic chain `0001_initial_schema` →
`0002_drop_gun_master_score` → `0003_request_gates` contain no
watchdog run lease. Existing `collectors.last_heartbeat_at` describes
collector activity and cannot attest to independent watchdog health.
Existing watchdog and local guard both enforce `0003_request_gates`.
Changing the schema head without updating both guards and the other
revision-pinned operational scripts would make preflight fail. Do not
apply a migration until compatibility and rollback are addressed.

## Proposed state model

A dedicated `stage9c_supervision_runs` table, introduced by a **future**
migration, stores one immutable run UUID per explicitly authorized six-hour
execution. Proposed columns (not yet present in PostgreSQL):

- `run_id uuid primary key`
- `state text not null`: `prepared`, `active`, `aborted`, `completed`
- `cutover_at timestamptz not null` and `since_event_id bigint not null`,
  fixed to the accepted Stage 9B boundary for Stage 9C
- `started_at timestamptz`, `deadline_at timestamptz` (set once at
  activation; exactly six hours apart)
- `watchdog_owner uuid` and `watchdog_generation bigint not null`
- `heartbeat_at timestamptz` and `lease_expires_at timestamptz`
- `abort_at timestamptz`, `abort_reason text`
- `created_at timestamptz not null default now()`, `updated_at timestamptz
  not null default now()`

Database time (`clock_timestamp()`) is authoritative for all lease
freshness comparisons and deadline checks; no host-local wall clock is
trusted for authorization. Use a DB check constraint for legal states,
deadline ordering, and terminal abort metadata. The actual migration must
specify and test constraints explicitly.

## Proposed authorization contract

1. **Explicit activation only.** A launcher supplies an exact `run_id`
   to the watchdog and all guards. Merely finding the newest active row
   must never authorize a host. Activation requires the expected cutover
   and event boundary, no other active run, and a fresh preflight.
2. **Single writer/fencing.** Watchdog acquires ownership atomically.
   Every heartbeat update is conditioned on matching `run_id`,
   `watchdog_owner`, `watchdog_generation`, `state='active'`,
   and unexpired prior lease. Lost ownership or an expired lease must
   terminate the watchdog; it must not silently reacquire and resume
   production. A new run requires operator authorization.
3. **Heartbeat cadence:** propose every 5 seconds, lease TTL 20 seconds.
   The watchdog must complete safety inspection **before** extending the
   lease; do not renew an unverified run. A guard checks at most every
   5 seconds. Worst-case detection under normal scheduling is about
   25 seconds after the last successful heartbeat; DB stalls and OS
   scheduling require bounded query timeouts and independent systemd
   deadlines. These are design targets, not measured guarantees.
4. **Guard validation:** verify database/revision/primary and collector
   identity, then in the same inspection require the exact run UUID,
   active state, matching frozen boundary, `lease_expires_at >
   clock_timestamp()`, and `clock_timestamp() < deadline_at`.
   Missing state, timeout, wrong run, expired lease, or terminal state
   causes immediate local stop. The tcou guard stops both collector and
   materializer. The dependent systemd units stop if the guard exits.
5. **Sticky abort:** on any confirmed safety fault, atomically transition
   `active → aborted` and record the reason, then drain all three
   collector registrations. If the database is unreachable, guards
   independently stop on DB failure or lease expiry. Terminal states
   cannot be reset to active; a process restart cannot clear an abort.
6. **Six-hour end:** guards independently enforce the DB deadline;
   systemd `RuntimeMaxSec` on guard and workers provides a secondary
   bounded-runtime backstop. Stop collector processes before final
   materialization shutdown and audit. No automatic Stage 9D.
7. **No historical data mutation:** the lease table is separate from
   `collection_jobs`, `collection_events`, and `request_gates`.
   Existing job 6722, event boundary 11558, and retry debt remain intact.

## Failure modes to prove before activation

- Watchdog SIGKILL while DB remains healthy: heartbeat expires and
  **all three** guards stop dependent workers.
- Watchdog alive but inspection fails: heartbeat is not renewed;
  sticky abort when DB permits; all guards stop.
- PostgreSQL unavailable to one host: that host's guard stops immediately.
- PostgreSQL unavailable fleet-wide: all guards stop without depending
  on a database drain transaction.
- Watchdog lease owner replaced or generation mismatched: stale writer
  cannot renew, stale guards cannot authorize a different run.
- 403/429 or persistence abort: terminal state persists and tcou
  materializer stops as well as all collectors.
- Guard SIGKILL: its dependent worker stops through systemd `BindsTo=`.
- Deadline reached: every host stops even if watchdog keeps running.
- Guard restart with an aborted/expired run: no worker resumes.

## Implementation gate

Before adding migration `0004`, audit all exact Alembic revision checks
and the operational scripts that depend on them. Update
`docs/database-schema-reference.md` in the same change set as the
migration. Add offline SQL/state-transition tests, then isolated
PostgreSQL integration tests and harmless three-host systemd fault
injection. **No production migration or live launch is approved here.**
