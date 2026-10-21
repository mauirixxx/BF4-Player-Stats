# Stage 9C D2 three-site soak recovery design

Status: implementation reference; production BF4PS deployment remains HOLD.
Scope: isolated D2 scratch database and the three physical soak nodes tcou, kah-01, hnl-01.
Historical run: bf4ps-d2-three-hour-soak-20261011-v1. Preserve its evidence; never reset it as part of a code fix.

## Observed failure (2026-10-11 UTC)
- PostgreSQL 16/main on mak-db-02 rejected bf4ps_stage9c_d2 connections at 20:59:07 and 21:16:38 UTC: only superuser-reserved slots remained.
- Server setting snapshot after the run: max_connections=100, superuser_reserved_connections=3, reserved_connections=0; 53 pg_stat_activity rows including replication/background workers. This snapshot does NOT establish the historical connection owner.
- Durable D2 evidence: 51 collection_attempt_started and 51 collection_success events; hnl-01 36/36, kah-01 12/36, tcou 3/36; rounds 1-5 completed, round 6 enqueued, run stopping, 2 pending and 1 running collection_jobs.
- Supervisor creates one engine for its lifetime; guarded work(node) creates a new engine each invocation and does not explicitly dispose it. SQLAlchemy QueuePool defaults may retain connections while engines are alive. Engine churn is a suspected contributor, not yet proven as the sole cause.
- Worker loop propagates unexpected SQLAlchemy OperationalError; site-budget exhaustion is also fatal. A surviving site can consume its allocation while peers are unavailable.
- Coordinator logs pre-transition run.state as SOAK STOP running even when stop() changes state to stopping.

## Safety invariants
1. Preserve PostgreSQL atomic pre-HTTP admission, advisory transaction lock, per-site 36 and global 108 physical-attempt ceilings, deadline, database identity/revision, hostname, cohort and run-state checks.
2. No automatic replay of an uncertain HTTP attempt; reconnect only for database-only operations before HTTP admission, or after durable state is reconciled. Never treat connection loss after admission as permission to reissue an external request.
3. No silent fail-open if the database is unavailable. Never bypass pre_http_admission.
4. Changes must not auto-ignite, reset, clean up, or alter the historical run. Any future test requires fresh explicitly approved run ID and separate authorization for real Battlelog requests.
5. Production BF4 Server Watcher connections and HA replication are out of scope. Do not restart PostgreSQL or modify max_connections as part of this patch.

## Implementation order
A. Engine lifecycle: create one bounded SQLAlchemy engine per long-running worker process, reuse across iterations, dispose in finally; ensure coordinator disposes too. Prefer small pool_size and max_overflow=0 for D2, pool_pre_ping and bounded pool_timeout. Account for one engine per process, not one per iteration.
B. DB fault tolerance: classify transient SQLAlchemy connection failures; bounded exponential retry/backoff with jitter for preflight/polling only; log errors and recover on a fresh transaction. Do not swallow identity, revision, safety gate, or invariant errors. Treat per-site budget exhausted as terminal, explicitly logged, without a new HTTP attempt.
C. Scheduling fairness: avoid allowing a healthy site to take over all other sites' intended jobs when peers are down; enforce node-to-cohort assignment at selection/admission. Verify current query semantics before coding this.
D. Terminal reconciliation: distinguish completed, stopped/deadline, and failed; do not call a 5/12 run completed. Account for orphaned running leases without fabricating success. Reconciliation must be guarded, idempotent, and auditable.
E. Tests: offline failure-injection tests for transient DB outage, admission failure, post-admission ambiguity, per-site exhaustion, three-node fairness, deadline, stale lease, and no additional physical requests; run static checks and unit tests before any live test.

## Acceptance criteria
- Three workers stay alive through temporary DB connection pressure or exit cleanly at deadline/site budget; no unhandled tracebacks for expected transient errors.
- Concurrent live database sessions are predictably bounded; no per-iteration engine churn.
- Each site performs only its assigned cohort work and cannot drain another site's budget.
- HTTP gate invariants unchanged; every recorded physical attempt has one durable admission, no duplicate on retry.
- Run final status and incomplete jobs are explained by an explicit reconciliation report.
- Offline tests pass on the branch; no production or real HTTP changes without a separate operator go/no-go.
