# Stage 9C D2 — scratch schema verification (2026-10-10)

**Scope:** read-only verification through Desktop Commander on `tcou`, against the explicitly configured `bf4ps_scratch_stage9c_integration` database on `mak-db-02.bf4statusbot.com`. **Production HOLD.** No migration, DDL, data write, or HTTP collection.

## Identity and safety

The existing `scripts.phase5b_stage9c_t4_host_preflight --check --expected-host tcou` passed, confirming the expected primary identity, role, Alembic head, and empty fixture tables covered by the preflight. Its output explicitly reported zero SQL writes and zero HTTP.

An independent `information_schema.columns` query confirmed `alembic_version = 0004_stage9c_supervision_runs` and columns for `collection_jobs`, `collection_events`, `request_gates`, and `stage9c_supervision_runs`. An independent `pg_indexes` query confirmed:

- `collection_events`: primary key `event_id`; operational indexes by job/time, type/time, and other dimensions. **No unique index on logical dispatch attempt.**
- `collection_jobs`: primary key `job_id`; unique `(soldier_id, resource)`; claim and expired-lease indexes.
- `request_gates`: primary key `egress_key`.
- `stage9c_supervision_runs`: inspected columns include `run_id`, `state`, `watchdog_owner`, `watchdog_generation`, and `lease_expires_at`.

These observations agree with the relevant schema reference and migration head; they do **not** prove the safety of a new dispatch ledger, transaction ordering, or physical HTTP timing.

## D2 implications

1. A distinct ledger with a database-enforced unique dispatch identity is justified; existing operational events do not provide it.
2. The existing `collection_jobs` row is mutable, so historical dispatch identities must survive lease replacement and normal queue progress.
3. D2 must reconcile overlapping reservation, start-event, and dispatch evidence without double counting and without prematurely expiring later dispatch timestamps.
4. Existing egress gate is a pacing primitive, not an atomic network-send authorization.
5. PostgreSQL admission cannot alone guarantee a rolling-hour bound on *actual* HTTP when workers may pause indefinitely after admission.

## Next safe step

Review the new ledger's immutable identity, retention policy, timestamp rule, and fail-closed replay semantics. Design scratch-only migration after that review. Do not integrate with collectors or activate production traffic without a separate gate.
