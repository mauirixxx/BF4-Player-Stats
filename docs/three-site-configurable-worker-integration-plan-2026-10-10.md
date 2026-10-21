# Phase 5B — Three-site configurable-worker integration plan (2026-10-10)

## Intent
Validate distributed PostgreSQL job claiming across **tcou**, **kah-01**, and **hnl-01** using a configurable number of independent worker processes. Eight is a baseline configuration, **not** a fixed architectural limit. Test 3, 8, 16 and optionally 32 workers, including graceful scale-down and failover.

## Confirmed host readiness
- tcou: validation checkout and D2 scratch credentials already configured.
- kah-01 and hnl-01: validation checkouts and Python SQLAlchemy virtualenv present; resolve mak-db-02.bf4statusbot.com to 192.168.10.78. Their validation checkouts were at test/stage9c-admission-concurrency, d5cae1d when inspected.
- **Neither remote host had /root/.config/bf4ps/stage9c-d2.env** when inspected. Do not copy secrets into repositories or logs. Provision narrowly scoped D2 credentials out of band before running cross-site write tests.
- Existing production BF4 Server Watcher workers on kah-01 and hnl-01 must not be interrupted or modified.

## Safety gates
1. **Production HOLD.** Never enable Battlelog HTTP, production database writes, migrations, or live collector scheduling.
2. Use only the dedicated `bf4ps_scratch_stage9c_d2` scratch database with exact DB/user/IP and migration validation on **every** participating host.
3. Keep `bf4ps_scratch_stage9c_integration` untouched.
4. All synthetic records must have unique markers and scoped cleanup; fail closed on unexpected pre-existing data or identity mismatch.
5. No shared filesystem assumptions. Each process needs a unique collector UUID, hostname snapshot, and synthetic egress label. A synthetic egress label is **not** a distinct public IP.
6. The global physical-send budget of **1296 actual dispatches in any rolling 3600 seconds** remains unresolved and unchanged; SQL claim success does not authorize an HTTP dispatch.

## Test protocol
1. Prepare a coordinator-only synthetic cohort on D2, including jobs in fresh, retry-eligible and cooldown states. Publish a run marker, expected job IDs and a start barrier time.
2. Launch processes from all three hosts using a configurable distribution, initially `tcou=3, kah-01=3, hnl-01=2`. Each process uses a separate PostgreSQL connection and collector UUID; claim using existing `claim_next_job`.
3. Synchronize contenders by a **database-side** barrier or bounded scheduled start. Each worker attempts claims and records results in a scoped run record. Never interpret host-local clocks as globally synchronized.
4. Verify each (job_id, attempt_count) has **at most one committed claim owner**, check lease tokens, and count distribution by host and worker. Include zero-eligible/cooldown cases.
5. Repeat at 3, 8, 16 workers; optionally 32 after DB connection-pool limits and safety checks. Test abrupt process exit, expired-lease reclaim, graceful drain, and 16→3 scale-down.
6. Report job counts, distinct claimed IDs, duplicate claim count, retry ordering, claim latency percentiles, lease recovery time, and PostgreSQL errors.
7. Stop workers and perform scoped cleanup. Independently verify all synthetic tables empty. Do not drop schema objects.

## Required implementation before execution
- Multi-host runner with coordinator setup/cleanup, a worker-only CLI, bounded runtime, run markers, synchronization and result collection.
- Preflight on kah-01 and hnl-01 for D2-only credentials without printing connection strings, and exact database identity verification.
- Isolated validation worktrees or fast-forward-only branches, avoiding changes to existing production deployment directories.
- Explicit operator approval before running the first cross-host **scratch database write** exercise.

## Interpretation
A successful three-host test proves cross-site PostgreSQL coordination, **not** eight independent public egress IPs or physical HTTP rate-budget enforcement. Those require separate evidence.
