# Stage 9C D2 three-hour soak — restart-safety design gate

**Status: required before autonomous ignition.** This supplements the [three-hour soak design](bf4ps-three-site-three-hour-soak-design-2026-10-11.md). No production migration is authorized.

## Critical discovery

The current `scripts/stage9c_three_hour_soak_control.py` can enqueue round 1, but its duplicate-round check looks for `collection_events.metadata->>'soak_reason'`. The existing detailed collection events do **not** populate that metadata key. After a completed job is removed from `collection_jobs`, its original `reason` is not retained in the collection event ledger. Therefore a local JSON manifest alone cannot safely prove which rounds were previously enqueued after a crash.

**Do not execute `prepare-round --execute` or start unattended workers until the persistent round identity and recovery protocol are implemented and tested.** In particular, a successful status/preflight command does not validate restart safety.

## Durable PostgreSQL run/round ledger (isolated D2 only)

Implement an explicitly documented, Alembic-migrated schema with:

- `soak_runs`: unique `run_id`, immutable nine-soldier cohort digest, event baseline, total physical-attempt ceiling, site ceilings, UTC start/deadline, state, stop reason, and creation/update timestamps.
- `soak_rounds`: unique (`run_id`, `round_number`), planned UTC eligibility time, state, enqueue timestamp, and immutable nine-job attribution.
- `soak_round_jobs`: unique (`run_id`, `round_number`, `soldier_id`), queue `job_id` and final outcome. Each enqueue and corresponding round-job ledger insertion must commit in the **same transaction**.
- Unique constraints and row locks must prevent two coordinators from admitting the same round or exceeding its scheduled eligibility. Only the designated `tcou` coordinator may mutate round state.
- Persist `job_id` attribution so completed, deleted queue jobs can still be matched to the durable collection-events ledger. A completed round is determined by the nine attributed jobs' terminal events and the absence of outstanding jobs, not by the coordinator's local JSON.
- Explicit reconciliation after a crash: DB ledger wins over local manifest. A mismatch halts admission; no automatic reenqueue or guessing.

## Request accounting and recovery

- Use the same atomic global-attempt claim mechanism already proven in Stage 9C; count physical attempts across the entire run and account for in-flight reservations.
- A failed/abandoned HTTP request still consumes the global ceiling. Do not assume that 108 enqueued jobs imply exactly 108 HTTP requests when retries/reclaims exist.
- Site-specific ceilings must be enforced **before HTTP**, not merely audited afterward. If a site reaches 36 attempts, it stops claiming; other sites may continue only within the global 108-attempt limit and without increasing their own 36-attempt caps.
- Round admission requires the previous round's terminal reconciliation and a fresh budget check. If any job cannot complete within the remaining attempt budget, halt the run with an explicit failed/incomplete outcome rather than silently extending the budget.
- A deadline must be enforced by each worker before starting an HTTP request. The coordinator's stop flag alone cannot stop disconnected workers.
- Existing per-site `egress_key` gating and production-background admission remain mandatory.

## Required validation

1. Live read-only schema inventory; compare migration design with documented schema before implementation.
2. Unit tests: duplicate admission, interrupted transaction, coordinator crash after DB commit but before manifest write, duplicate coordinator, expired deadline, site ceiling, global ceiling, and failed request.
3. D2 integration: prepare one round without HTTP, kill/restart coordinator, prove no duplicate enqueue; clean up only attributed scratch rows.
4. Three-site dry-run status/preflight; explicitly authorize ignition after all gates pass.

No changes to BF4SW production, no extra soldiers, no unattended daemon yet.
