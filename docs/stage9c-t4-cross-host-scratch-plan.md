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
