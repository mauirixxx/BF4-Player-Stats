# Stage 9C D3: 900-job three-site PostgreSQL endurance design

Status: design checkpoint; implementation and multi-hour soak not yet approved as passing. Production HOLD. No outbound Battlelog HTTP.

## Proven baseline

On the isolated `bf4ps_scratch_stage9c_d3` database, 900 synthetic PC soldiers and 900 detailed/background jobs were enqueued. Three physical sites (`tcou`, `kah-01`, `hnl-01`) each committed 300 claims through `bf4ps.collection_jobs.claim_next_job` with a disjoint 300-soldier allowlist. Independent PostgreSQL inspection showed 900 claimed jobs, exactly 300 per site, each attempt_count=1, no cross-site ownership. Site times were approximately 0.783, 22.010 and 18.862 seconds, respectively. The three collectors and claimed jobs are intentionally retained. Claims expire after their 3600-second lease; expiration does not itself revert status to pending.

## Safety invariants

1. Database URL must be identical in `BF4PS_DATABASE_URL` and `BF4PS_STAGE9C_D3_URL`; parsed database must be exactly `bf4ps_scratch_stage9c_d3`. Server must report matching `current_database()`, `current_user()=bf4ps_stage9c_d2`, `pg_is_in_recovery()=false`, and expected Alembic revision `0006_stage9c_soak_round_ledger` before any write.
2. Never touch D2 historical evidence, any BF4SW production node, or production BF4PS. No network requests to Battlelog, Keeper, BFLIST or any external statistics provider.
3. Cohort ownership derives from the exact D3 synthetic soldier name prefix per site; validate 300 distinct IDs/site and 900 total. Each claim MUST pass `allowed_soldier_ids` to the production claim function. Never use unrestricted claims.
4. Persist immutable run evidence (run UUID, code revision, UTC start/end, host, per-worker claims, releases, lease losses, exceptions, connection errors, latency distributions, database snapshots, and validation decisions) outside the D2 validation checkout.
5. Reset is a distinct operator-controlled D3-only operation. Capture pre-reset evidence first; verify all 900 expected D3 synthetic jobs, exactly 3 site cohorts, no active D3 test workers, and expected collector identities. Never reset by time alone.
6. Limit connections per host, pool overflow zero, bounded transaction duration and retry/backoff. Fail closed on schema, identity, cohort, or invariant mismatch.

## Endurance phases

- Phase A: implement `preflight`, `snapshot`, `reset`, `worker`, `verify` CLI, with unit tests for identity/cohort gates and lease-token fencing. Reset must be opt-in `--execute` and preserve evidence before mutation.
- Phase B: single-site 10-minute dry run using claim + token-fenced `release_for_retry` with no HTTP. Measure connections and retry behavior. Require zero unexplained failures before three-site operation.
- Phase C: synchronized three-site 30-minute shakedown, bounded per-site worker pools; validate no duplicate simultaneous ownership, no cross-site claims, bounded connection count, no unowned jobs, no lease-token violations.
- Phase D: 3–4-hour three-site endurance with deliberate worker stop/restart, lease expiry and recovery, PostgreSQL connection pressure and optional controlled database failover only after separate authorization. Failover must not be conflated with ordinary workload testing.
- Phase E: replay authentic previously captured Battlelog payloads offline through actual parsing and persistence. Keep HTTP disabled; verify idempotency, row/history growth and crash recovery. If fixtures do not exist, acquire them only after separately passing physical outbound-dispatch safety gates and receiving explicit authorization.

## Metrics and exit gates

Track claim/release rate per site and per worker, SQL transaction latency (p50/p95/p99), database active/idle/max connections, lock waits, deadlocks, lease expirations/reclaims, retries, errors, and disk/WAL growth. Required: zero cross-site ownership, zero double ownership, zero unaccounted jobs, zero exhausted pools, zero uncaught worker exits, zero stale-token mutations, and reconciled durable per-run reports. Connection-pool configuration and any throughput target must be explicitly recorded; do not infer them from the 900-claim baseline.

## Current operational note

The 900 jobs are in `claimed` state with one-hour leases and attempt_count=1. A new claim can reclaim them only once their leases expire, increasing attempt_count. Preserve this baseline and inspect before any reset. The 900-claim exercise was a one-shot workload, not an endurance run or realistic statistics-write benchmark.
