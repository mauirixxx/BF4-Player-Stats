# Phase 5B — Three-site synthetic soak gate (design, 2026-10-11)

Status: **design approved for implementation only; production HOLD**. Source of truth: documented D2 schema, `scripts/phase5b_three_site_manifest.py`, `scripts/phase5b_three_site_d2_coordinator.py`, `bf4ps/collection_jobs.py`. Verify schema against D2 before extending SQL.

## Objective
Run a 30-minute shakedown followed by a four-hour soak on tcou (3 workers), kah-01 (3), hnl-01 (2), using **synthetic PostgreSQL D2 work only**. Host counts are configuration, not hard-coded. This does not validate live BF4 collection throughput or API safety.

## Safety invariants
1. `bf4ps_scratch_stage9c_d2` / `bf4ps_stage9c_d2` identity preflight before any mutation; explicit `--execute`; no production DB, migrations, network HTTP, or Battlelog.
2. Immutable digest-verified manifest and explicit state-bound soldier/job cohort. Each host verifies its own collector identity and allowed soldier IDs in D2 before claiming.
3. Bounded wall-clock duration, bounded per-worker attempts, fixed pacing and jitter, fail-closed on DB errors or invalid cohort; record failures. Do not turn unexpected exceptions into success.
4. Worker shutdown on SIGTERM/SIGINT: stop claiming, release only currently owned work using fencing tokens, emit atomic JSON report. Crash recovery: lease expiry and reclaim by another host; stale owner must not renew, finalize, or overwrite.
5. Per-cycle jobs are claimed, marked running, then **released to pending** with a bounded eligibility delay; no HTTP and no stats persistence. Claim/release uses the existing `collection_jobs` API, not raw unscoped SQL. Repeated claims increase attempt_count; these are synthetic lease iterations, not API requests or user-visible duplicate fetches.
6. Do not run coordinator cleanup while any worker remains active. Stop all hosts, confirm all processes exited, reconcile cohort against D2, then cleanup. Guard cleanup with manifest/state/intent; all five core tables must be empty afterward.
7. Do not print credentials, connection URLs, or raw environment variables. Store per-host JSONL heartbeat and summary files in root-owned restricted paths; capture host, collector UUID, iterations, errors, lease losses, p50/p95 claim latency, timestamps, and D2 status counts.
8. **Production remains on HOLD**. The global 1296 physical HTTP dispatches per rolling hour remains unresolved and unchanged.

## Execution gates
- Preflight: clean D2, correct code revision on all three hosts (remote hosts use temporary worktrees), verified DB auth, all eight workers ready, clock skew measured.
- Shakedown: 30 minutes, eight workers, periodic metrics (60 seconds), injected single-worker SIGKILL after its first committed claim; another host reclaims only after lease expiry. Confirm no overlapping valid owner, no unbounded retry storm, no leaked processes.
- Four-hour soak only after shakedown PASS. Sample host/process liveness and DB state each minute. Require all eight workers participating; exactly one owner per job at every observation; no HTTP; no unexplained exceptions; no runaway DB connection growth; complete cleanup.
- Stop immediately for identity mismatch, non-synthetic cohort, unexpected HTTP, DB corruption, invalid ownership, or unbounded error rate.

## Reporting
A run is PASS only with durable reports from all planned workers, final D2 ownership/retry reconciliation, recorded crash recovery, verified host exit, and clean five-table D2 state. A launch or elapsed time alone is not a PASS.

## Implementation sequence
1. Add guarded soak worker with bounded loop, clean shutdown, structured reports and tests.
2. Add orchestrator/read-only status + reconciliation; make crash injection opt-in and isolated.
3. Execute a short 3-host shakedown, then 30 minutes, then four hours. No long-running task should be launched without explicit duration, stop controls, and reliable observation.
