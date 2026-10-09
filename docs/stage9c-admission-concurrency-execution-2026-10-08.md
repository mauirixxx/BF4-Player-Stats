# Stage 9C admission concurrency — operator execution record (2026-10-08)

Status: **PARTIAL PASS — production Stage 9C remains HOLD**.

## Provenance and safety boundary

- Operator host: `tcou`.
- Isolated checkout: `/opt/bf4ps-stage9c-validation`; branch `test/stage9c-admission-concurrency`; tested commit `821dfb5`.
- Existing `/opt/bf4-player-stats` checkout was left unchanged.
- Target: `mak-db-02.bf4statusbot.com` (`192.168.10.78`), PostgreSQL port 5432, database `bf4ps_scratch_stage9c_integration`, user `bf4ps_stage9c_integration`.
- Read-only preflight verified: exact database/role/server IP; `pg_is_in_recovery()=false`; `transaction_read_only=off`; Alembic `0004_stage9c_supervision_runs`; all five fixture tables empty.
- No production database, systemd action, migrations, or outbound Battlelog requests were involved.

## Offline gate

- Harness compile: PASS.
- Targeted Stage 9C contracts: **6 passed**.
- Full offline suite: **412 passed** (SQLAlchemy 2.1.4, pytest 8.4.2).
- Git working tree: clean.

## Real PostgreSQL claim race

Initial direct-path invocation failed before execution with `ModuleNotFoundError: No module named 'scripts'`. Correct command from repository root:

```bash
.venv/bin/python -m scripts.phase5b_stage9c_claim_race_scratch --execute
```

Operator-reported output:

```text
PASS: real production claim at 1295 reserves final slot
PASS: independent competing vehicles claim denied at 1296
PASS: committed reservation and lease ownership reconciled
Battlelog requests: 0
PASS: exact scratch fixture cleanup
HARNESS EXIT CODE: 0
```

The test exercised two independent transactions calling the production `claim_production_background_job` path for weapons and vehicles. A held winning transaction and production advisory-lock probe enforced the race boundary. The first claim reserved the final slot; the second claim was denied after the committed reservation became visible. The winner's lease ownership was reconciled.

## Independent cleanup verification

Operator independently queried the scratch database after execution:

```text
collectors: 0
soldiers: 0
collection_jobs: 0
collection_events: 0
stage9c_supervision_runs: 0
PASS: Scratch database clean after claim race
```

## Scope and unresolved gates

**This is one successful scratch concurrency scenario, not Stage 9C production acceptance.** Still required: reservation-to-start replacement accounting; expired unstarted and started lease reclaim; retry consumption; mixed-resource and retry races; rollback/failure paths; exact rolling-hour expiry; physical-start ledger completeness; host-local guard/systemd safety; independent deployment preflight; and explicit operator authorization for any six-hour production trial.

Do not rerun or extend scratch tests without rechecking the documented schema, migration head, target allowlist, fixture ownership, and cleanup/failure behavior. Preserve **HOLD**.
