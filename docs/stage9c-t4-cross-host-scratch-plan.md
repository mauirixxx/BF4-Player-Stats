# Stage 9C T4 — cross-host scratch admission validation plan

Status: **PROPOSED / NOT AUTHORIZED**. Design-only checkpoint; production Stage 9C HOLD.

## Purpose and evidence boundary

T1/T2/T3 were validated on tcou using isolated PostgreSQL scratch and independent cleanup. T4 must demonstrate that distinct physical hosts (tcou, hnl-01, kah-01) coordinate through the same PostgreSQL primary, not merely through separate tcou connections. No claim of cross-host PASS exists yet.

## Allowed target and participants

- Coordinator: tcou; remote participants: hnl-01 and kah-01.
- Scratch DB only: mak-db-02.bf4statusbot.com / 192.168.10.78; database bf4ps_scratch_stage9c_integration; user bf4ps_stage9c_integration.
- Expected schema head: 0004_stage9c_supervision_runs.
- Each remote process must independently verify hostname, DB name/user/server IP, pg_is_in_recovery=false, transaction_read_only=off, Alembic head, READ COMMITTED isolation, and authorized scratch URL. Do not print credentials.
- Hostname identity and route/egress independence must be confirmed by operator evidence, not inferred from labels.

## Non-negotiable boundaries

1. No commands on remote hosts until explicit operator approval after reviewing this plan and the exact harness.
2. Zero Battlelog HTTP, no live external collection, no production DB connection, no production collector rows, no migration or service activation.
3. No systemd unit changes, no Docker operations, no production collector start/stop.
4. Scratch preflight requires zero rows in collectors, soldiers, collection_jobs, collection_events, stage9c_supervision_runs. Refuse if unexpected activity appears.
5. Use an explicit unique run marker and narrowly scoped rows; fail closed on partial cleanup. Keep operator-provided connection secrets out of output and source control.
6. Set statement/connection timeouts and bounded barriers; no infinite waiting. Each process logs hostname, test phase, and pass/fail without credentials.

## Proposed sequence (design only)

1. Operator reviews/approves precise harness and execution window. Verify all three host checkouts and venvs at the same commit without modifying live services.
2. Coordinator performs strict scratch preflight, acquires fixture advisory lock, seeds a bounded three-resource cohort with synthetic identities and jobs, and records expected row IDs.
3. Each remote host runs a *dry-run* identity/preflight command first; inspect returned host and database identities. No writes on dry run.
4. At an explicit barrier, separate hosts compete for the final available global slot through the production claim/admission function in independent transactions. Assert exactly one successful claim and no oversubscription; log which host won.
5. Exercise one owner-bound start with the production start writer and assert a nonowner cannot start with the wrong lease; use only synthetic payloads and zero outbound HTTP.
6. Exercise one expired *unstarted* reservation reclaim under a controlled scratch clock/lease setup, asserting correct reservation accounting. Avoid broad failure-injection changes.
7. Coordinator reads the authoritative committed event ledger and usage, validates exact expected attempts, then performs exact-marker cleanup (events before jobs), checks all fixture rows removed, and reports PASS only after independent zero census.
8. Operator independently runs a read-only five-table census on the scratch database; any residue or unexpected rows means T4 stays OPEN.

## Abort and rollback

- Abort immediately on wrong DB identity, unexpected nonempty tables, host identity mismatch, missing barrier participant, timeout, unapproved egress, any real HTTP attempt, or inconsistent ledger.
- No remote production processes should be changed; rollback consists solely of deleting uniquely tagged scratch fixture rows, with explicit row-count assertions. Never TRUNCATE or DROP shared tables.
- On uncertain cleanup, stop all harness participants, retain logs/IDs, and require manual operator review before any further run. Do not perform blind retries.
- Keep T4 OPEN until the cross-host race, ownership, ledger, and independent cleanup evidence are all recorded.

## Approval checkpoint

This document authorizes **nothing**. Next deliverable is an exact reviewed, zero-HTTP cross-host harness and commands. Operator approval must be requested separately before any remote execution. T5 and O1–O4 remain OPEN; production Stage 9C HOLD.

## Implementation review checkpoint (2026-10-09)

- tcou read-only preflight passed; coordinator and participant syntax compilation passed on tcou at 810b749.
- Participant exact identity check patched at 92c6c65; coordinator expired-lease cleanup check patched at 9515971. These newer revisions have **not** been compiled or executed on a host.
- **STOP: do not execute seed/participant/inspect/cleanup yet.** There is no genuine cross-host readiness barrier or coordinator release protocol. The coordinator's current inspection only proves one claim and budget 1296; it does not prove three participants were concurrently ready or that all three returned.
- Current cleanup depends on operator confirming all participants exited, and on the winner's lease expiring. It does not yet independently establish participant completion or enforce a unique persistent readiness/finish ledger.
- Further review required: seed/participant SQL must be verified against the documented schema and migrations; exact expected fixture counts; failure cleanup on partial runs; independent read-only five-table census.
- Next engineering deliverable: add a bounded DB-coordinated ready/release/finished barrier using scratch-only durable state (no production migration), with explicit timeout/abort and no automatic rerun. Then run offline tests and a tcou-only rehearsal before seeking remote execution approval.
- T4 remains OPEN. No remote hosts or production systems were touched.

## Barrier implementation checkpoint — 2026-10-09

The test branch now contains `scripts/phase5b_stage9c_t4_barrier.py`, and revised coordinator/participant scripts. Each participant writes a distinct READY event, polls for one committed RELEASE for at most 60 seconds without holding an open transaction, performs one production admission claim, and commits a DONE event with WIN/DENIED outcome. Coordinator release requires three distinct READY events; inspect and cleanup require three distinct DONE events with one WIN and two DENIED. Cleanup expects exactly 1295 synthetic budget events plus seven barrier events and refuses an unexpired winner lease.

**Not yet validated**: latest syntax, scratch SQL, barrier behavior, exception/timeout cleanup, and actual cross-host concurrency. A timed-out or failed participant intentionally prevents automatic cleanup; manual incident review is required. The coordinator does not launch remote processes. No host execution authorized. This is a design and implementation checkpoint only. T4 OPEN; production HOLD.

## Three-independent-job correction (2026-10-09)

Review found that a single pending job cannot distinguish a global budget cap from ordinary duplicate-job locking. T4 now seeds three distinct soldiers and three independent pending detailed jobs, one assigned to each host. Each host claims only its own soldier. Expected result after RELEASE: one claimed job with attempt_count=1, two still-pending jobs with attempt_count=0, and shared usage 1296/1296. This is a test-design correction, not yet a tested result. Changes at ed99aa5 and 18556b9. Recompile latest scripts before any database rehearsal. Cross-host authorization remains withheld.

## Failure handling and time-window checkpoint (2026-10-09)

- Release now checks that exactly 1295 synthetic `collection_attempt_started` events remain and that their oldest timestamp is no more than five minutes old. This is stricter than the rolling one-hour budget and prevents delayed release from giving misleading results. Change: f473ef2.
- **Normal path:** three READY events, one RELEASE, three DONE events, inspect, then cleanup only after winner lease expiry and confirmation that all participant processes exited; independently count all scratch fixture tables afterward.
- **Failure before release:** no admission attempt should have occurred. The existing `cleanup` command deliberately refuses because there are not three DONE events. Do **not** bypass it or rerun `seed`. Record event/job/lease state and stop participants before designing an exact, reviewed recovery transaction.
- **Failure after release:** a winner might hold a valid lease even if its DONE event was not committed. Stop all participants, preserve evidence, inspect ownership and expiry, and do not delete rows until a separate reviewed recovery plan explicitly covers missing DONE events.
- **Rolling-hour expiry:** if synthetic events age out before inspection, treat T4 as inconclusive rather than PASS; preserve fixture for forensic review. Never add synthetic events mid-run.
- **Current blocker:** no implemented, reviewed recovery command for incomplete READY/RELEASE/DONE sequences. No functional scratch rehearsal or cross-host execution authorization yet. Production HOLD.

## Read-only incomplete-run diagnostic (2026-10-09)

New `scripts/phase5b_stage9c_t4_diagnose.py` provides read-only, repeatable-read scratch diagnostics of collector, soldier, job, lease and READY/RELEASE/DONE events for a specified UUID. It performs no cleanup or lease release. It has not yet been validated on tcou. This is a forensic aid, **not** a complete recovery path. Cleanup of incomplete runs remains blocked pending reviewed participant-exit verification, ownership checks, and post-cleanup census. Do not run the fixture yet. Production HOLD.

## Diagnostic --check checkpoint (2026-10-09)

`python -m scripts.phase5b_stage9c_t4_diagnose --check` is the next proposed **read-only** tcou validation. It uses a repeatable-read, read-only transaction to verify scratch target identity, migration revision, diagnostic queries, and zero rows in collectors, soldiers, collection_jobs, collection_events, and stage9c_supervision_runs. No UUID, fixture seed, participants, release, HTTP, or remote host execution is required. It is not yet runtime-validated; a syntax pass alone is insufficient. If any table is nonempty or the database identity differs, stop and inspect without cleanup. Recovery cleanup remains unimplemented and T4 remains OPEN.

## Partial-run recovery implementation checkpoint (2026-10-09)

The scratch-only coordinator now accepts a separate `recover` action (commit `2011039`). It requires `--execute --run-id UUID --confirm-all-participants-stopped --confirm-preserved-evidence`. **These flags are operator attestations, not automated process verification.** Do not use them until the operator has confirmed all three processes have exited and saved the read-only diagnostic and host logs.

Recovery refuses a fully completed three-READY/one-RELEASE/three-DONE run (use normal cleanup), malformed host identities, duplicate or unexpected ledger records, unrecognized event types, unexpected synthetic event counts, multiple admitted jobs, and unexpired claimed/running leases. Deletions remain in a single PostgreSQL transaction with exact rowcount checks; any exception rolls back. It never performs HTTP or remote execution.

**Still unvalidated:** the recovery implementation has not passed a tcou syntax check or scratch failure-injection tests. Its assumptions about concurrent process exit depend on external operator evidence. Before authorizing fixture execution, add targeted offline recovery tests and inspect all SQL against the documented schema. Preserve the independent post-cleanup five-table census requirement. T4 OPEN, production HOLD.

## Cleanup referential-integrity audit (2026-10-09)

Commit `c115cef` adds fail-closed pre-delete checks against the documented `collection_events.job_id`, `collection_events.soldier_id`, `collection_events.collector_uuid`, and `collection_jobs.soldier_id` relationships. An unmarked event linked to a fixture identity, a fixture job owned by an unknown collector, or an unrelated job on a fixture soldier blocks both normal cleanup and recovery before any DELETE. This protects event evidence from FK SET NULL and unrelated jobs from FK CASCADE.

These checks have not yet been syntax-checked on tcou or exercised with PostgreSQL fixture mutations. The existing offline recovery rule suite (15/15) does not cover these new SQL guards. **Do not run cleanup/recover/seed** until targeted scratch rollback tests and independent census are complete. T4 OPEN, production HOLD.

## Cleanup reference guard offline test checkpoint (2026-10-09)

The SQL reference checks are extracted to `scripts/phase5b_stage9c_t4_cleanup_guards.py`, called by the coordinator before DELETE. They reject both unmarked events linked to fixture identities and marked events linked to foreign identities, foreign job owners, and unrelated jobs on fixture soldiers. `tests/test_stage9c_t4_cleanup_guards.py` provides five offline fake-connection tests. These validate query order and refusal logic but **not** PostgreSQL semantics or transaction rollback; run them on tcou before further work. A PostgreSQL scratch fixture rollback rehearsal remains a distinct unapproved gate. Production HOLD.

## T4 rollback probe design (2026-10-09)

The coordinator has an opt-in `--rollback-probe` flag, valid only for `cleanup` or `recover`. After all normal identity, ledger, lease and reference guards pass, it performs the marker-scoped collection_events DELETE, checks the affected rowcount, then intentionally raises `RuntimeError("EXPECTED T4 ROLLBACK PROBE...")` **inside** the `engine.begin()` context. The exception must escape the transaction scope, causing rollback of the event deletion. No other fixture DELETE should execute. The command must exit nonzero; **a nonzero exit is expected, but is not itself proof of rollback**.

### Mandatory evidence before authorizing a scratch rollback probe

1. Separate operator approval for scratch fixture writes and the rollback probe; no remote host activity or production database connections.
2. Capture a read-only, transaction-consistent pre-probe census of the five fixture tables, plus marker-scoped event counts and identities. Retain the run UUID and logs.
3. Require all participant processes exited, all claimed/running leases expired, and a valid normal-cleanup or partial-recovery ledger. If the fixture is incomplete, the recovery confirmations are required.
4. Execute the exact approved command with `--rollback-probe` on tcou only; expect the explicit exception and nonzero exit.
5. Independently capture the same read-only census and marker-scoped event counts. They must match the pre-probe snapshot exactly. If any mismatch, STOP and preserve evidence; do not run ordinary cleanup.
6. Only after reviewing the probe evidence, separately approve normal cleanup/recovery and verify the independent five-table zero census.

**No fixture has been seeded and no rollback probe has been run.** This option is not a dry-run: it issues a DELETE inside a transaction and therefore must never be invoked without the explicit scratch rehearsal approval. T4 OPEN; production HOLD.

## Read-only rollback evidence capture and comparison (2026-10-09)

`scripts/phase5b_stage9c_t4_evidence.py` offers `--capture --run-id UUID --output NEW.json` and offline `--compare --before BEFORE.json --after AFTER.json`. Capture requires the pinned scratch connection identity and Alembic revision, then uses one `REPEATABLE READ READ ONLY` transaction to fingerprint **every row in each of the five fixture tables** using ordered JSONB text and SHA-256, plus marker-scoped event counts. The output file is created exclusively and never overwritten. Compare requires exact JSON evidence equality; it makes no database connection. Capture itself is read-only, but **do not run a rollback probe or fixture writes without separate operator authorization**. Run offline tests first. Evidence captures at different times can differ legitimately due to external changes; any difference blocks rollback PASS until investigated. This is not a substitute for independently verifying that participants stopped or leases expired.
