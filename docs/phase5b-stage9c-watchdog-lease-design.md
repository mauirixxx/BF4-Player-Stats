# Stage 9C — shared watchdog lease and sticky abort (design v1)

Status: **DESIGN + ISOLATED TEST EVIDENCE — scratch migration and transaction tests complete; no main-test/production migration, activation, or live processes authorized**.

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


## Revision compatibility audit — tcou output, 2026-10-08 UTC

After fast-forwarding to `d3683d2`, tcou reported **3/3** offline
migration contract tests passed. `git grep` identified hardcoded
`0003_request_gates` in the following categories:

- **Stage 9C live safety path:** `scripts/phase5b_stage9c_watchdog.py`,
  `scripts/phase5b_stage9c_local_guard.py`.
- **Operator control:** `scripts/bf4ps_production_collector_control.py`.
  The `drain` action must remain available after schema migration;
  `resume` must never bypass an active or aborted Stage 9C lease.
- **Step 9 read-only audits and activation tooling:** multiple
  `scripts/phase5b_step9*.py`, including checkpoint audit, activation
  readiness, rollback, and Stage 9B boundary.
- **Schema verifier:** `scripts/verify_database_schema.py`.
- **Historical Phase 2–5A harnesses and shared cohort constants:**
  deliberately pinned to the revision under which those experiments
  were accepted. Preserve historical expectations rather than blindly
  rewriting their constants.
- **Tests:** several tests assert exact `0003` string literals and
  must be revised only alongside their corresponding runtime policy.

### Upgrade policy

1. **Before database migration:** Stage 9C guards and watchdog must
   remain fail-closed against both schema versions until the lease
   implementation is complete. Do not broaden their accepted revision
   to `0004` before they actually enforce the lease.
2. **Operator emergency drain:** make `drain` compatible with both
   revisions while validating the same database and collector identity;
   retain strict safeguards for `resume`. An unqualified resume must
   not activate collection during Stage 9C.
3. **New Stage 9C launcher:** require exactly `0004` and prove the
   run lease and sticky abort checks before any live collector starts.
4. **Historical scripts:** keep pinned `0003` unless there is a
   separately reviewed reason to execute them against `0004`.
   A historical script refusing to run after upgrade is intentional,
   not permission to weaken its safeguards.
5. **Schema verifier:** support explicit target revisions with matching
   table/column expectations; do not call `0004` verified while
   only checking `0003` tables.
6. **Migration validation:** run Alembic offline inspection and isolated
   PostgreSQL upgrade/downgrade/upgrade tests with checks for no
   unexpected modifications to `collection_jobs`, `collection_events`,
   `collectors`, and `request_gates`. Production migration requires
   a separate approved window and a rollback plan.

**No production schema upgrade is authorized by this audit.**

## Stage 9C abort/drain failure gap — implemented; isolated transaction validation passed

**Observed in source review after the 9/9 dummy-systemd matrix:** `phase5b_stage9c_watchdog.py` calls `abort_owned_run()` and `drain_fleet()` in one `engine.begin()` transaction. `drain_fleet()` refuses missing or drifted collector registrations; the exception rolls back the run's `active → aborted` transition. The existing `test_drain_failure_rolls_back_abort` explicitly confirms this behavior. Lease renewal is withheld, so host guards should fail closed on expiry, but a confirmed safety violation is not recorded as a durable abort.

### Implemented fail-closed resolution and remaining boundaries

1. Keep the existing **atomic abort + complete three-collector drain** as the preferred path when identities are valid. Preserve owner/generation/cutover/boundary fencing and database-target validation.
2. On failure to commit that combined transaction, **do not renew the lease, restart collection, or infer that the abort committed**. A separate, narrowly scoped fallback transaction may commit **only** the fenced sticky abort of the exact run UUID, with the original safety reason plus a bounded drain-failure diagnostic. It must validate the same database identity, schema revision, run owner, generation, cutover, and event boundary. If fencing or database health is uncertain, refuse the fallback and rely on guard lease expiration.
3. Treat fallback abort as **terminal but fleet drain incomplete/unknown**. Do not report `ABORT + FLEET DRAIN` success, and do not mutate an unknown collector identity. Trigger explicit operator escalation; physical shutdown must be enforced by guards/systemd, not assumed from a database drain.
4. Prove through offline transaction fault injection that normal abort/drain commits together, a failed drain rolls back the combined transaction, and the separately committed fallback leaves the run aborted without claiming the fleet drained. Prove stale owner/generation, unavailable DB, and failed fallback do not falsely report success. Then use a disposable PostgreSQL database for real commit/rollback verification.
5. No live Stage 9C activation, production migration, or collector launch is authorized by this proposal.

**Tradeoff:** A fallback sticky abort cannot be claimed as an atomic fleet drain. The design deliberately favors durable terminal run state plus independent guard-enforced physical shutdown over silently rolling back a confirmed abort. Implementation and scratch transaction verification are complete for the tested paths; real process shutdown, end-to-end guard enforcement, and six-hour trial authorization remain outstanding.


## Stage 9C PostgreSQL abort/drain scratch integration — operator evidence, 2026-10-08

**Result: PASS, four checkpoints.** Operator ran `python -m scripts.phase5b_stage9c_abort_drain_scratch --execute` on tcou after pulling commit `59f3a1f8573764562c2b47a1aa1183050ca83952` from `feature/phase5a-cost-cohort`. Target was the explicitly allowlisted scratch PostgreSQL database `bf4ps_scratch_stage9c_integration` on `192.168.10.78`, user `bf4ps_stage9c_integration`, Alembic `0004_stage9c_supervision_runs`. The harness refused nonempty real collector/run registries, shadowed the collector registry with a PostgreSQL TEMP table containing three random UUIDs, and restored the production watchdog's target validator on exit. It did not run collectors, materializers, HTTP requests, systemd services, or migrations.

Observed terminal output:

```text
PASS: normal abort + all-three TEMP fleet drain committed
FENCED ABORT COMMITTED; FLEET DRAIN INCOMPLETE/UNKNOWN; operator intervention required
PASS: drift rollback followed by committed fenced abort; no drain claimed
PASS: stale owner and generation fenced
PASS: scratch cleanup; supervision ledger restored to zero
```

The critical fallback log line is **expected** for the deliberately injected identity drift. The tests verify (1) atomic commit of fenced abort plus three temporary drains; (2) rollback of combined abort/drain on identity mismatch, followed by separate durable fenced abort without claiming drain success; (3) stale owner and stale generation rejection; and (4) removal of test supervision rows. The fallback code is in `scripts/phase5b_stage9c_watchdog.py`; the disposable harness is `scripts/phase5b_stage9c_abort_drain_scratch.py`.

The initial scratch attempts exposed **harness-only** defects, all corrected before the passing run: separate `clock_timestamp()` calls violated the exact six-hour deadline check by one microsecond; the harness initially failed to activate its scratch-only target validator; and its fallback transaction adapter returned a SQLAlchemy transaction object instead of a connection. The production watchdog's strict database-target guard was **not** relaxed. The passing run used a single `transaction_timestamp()` to derive exact six-hour test deadlines.

**Evidence limits:** The scratch harness tests selected transaction paths, not the full watchdog `main()` loop or actual local guard processes. It does not establish that all three real collectors physically stop after fallback abort, that a failed fallback leaves guards fail-closed in real deployment, that DB outage/timeout scenarios work end to end, or that the rolling one-hour request budget is correct across the cutover. Previous offline supervision/fault-injection tests (21 passing on hnl-01) and dummy-systemd dependency tests (9/9 across tcou, kah-01, hnl-01) are complementary, not substitutes for those missing tests.

### Next pre-activation gate — rolling-budget boundary and end-to-end safety

1. Audit `scripts/phase5b_stage9c_watchdog.py` against the accepted Stage 9B cutover and event boundary. Its current `inspect()` selects only `collection_events.event_id > since_event_id` and calculates a rolling one-hour maximum from those starts. Verify whether pre-boundary attempts within the first hour must be counted toward the 1,296/hour ceiling; do not silently change the accepted budget policy.
2. Add offline tests covering starts just before/after the cutover, exactly at the one-hour boundary, and any documented event-order/timestamp edge cases. Prove fail-closed behavior if required pre-boundary evidence is missing or ambiguous.
3. Review guard/launcher/service deployment contract and exercise actual end-to-end termination with **dummy processes only**, without real BF4PS collectors, real database migrations, or Battlelog traffic. Request separate operator approval before installing or activating any additional services.
4. Reconcile this design's historical future-tense schema/migration language with the completed scratch-only `0004` implementation; never treat scratch migration success as authorization to upgrade the main test database.

**Gate remains closed:** no real Stage 9C activation or six-hour run has been authorized.
