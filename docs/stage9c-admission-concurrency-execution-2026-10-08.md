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

## Reservation-to-start execution — 2026-10-08

Operator executed `python -m scripts.phase5b_stage9c_reservation_start_scratch --execute` from the isolated `tcou` validation checkout at `7e22611`, after a passing 412-test offline regression and a read-only preflight showing zero rows in all five scratch tables.

Operator-reported results:

```text
PASS: production start event replaces committed reservation
PASS: aggregate usage remains 1296; next claim denied
Battlelog requests: 0
PASS: exact scratch fixture cleanup
HARNESS EXIT CODE: 0
```

**Evidence scope:** production detailed start-event writer was invoked against isolated scratch PostgreSQL with no outbound HTTP. It converted the winning committed reservation into one durable start event, kept aggregate accounting at the 1,296/hour ceiling, and denied another background claim. Harness-reported exact cleanup passed. **An independent post-run read-only emptiness check has not yet been reported** for this execution. Duplicate-start, lease reclaim, retries, mixed resources, rollback boundaries, and distributed hosts remain unproven. Production Stage 9C stays **HOLD**.

### Independent post-run cleanup verification

After the reservation-to-start execution, the operator ran a separate read-only PostgreSQL check against the allowlisted Stage 9C scratch database. All five tables returned **0 rows**: `collectors`, `soldiers`, `collection_jobs`, `collection_events`, and `stage9c_supervision_runs`. Output ended with `PASS: Independent scratch cleanup verification`. This closes the reservation-to-start fixture cleanup verification; it does not change the Stage 9C production **HOLD** or validate untested lease-reclaim scenarios.

## Expired unstarted lease at full capacity — reproduced defect

Operator executed `python -m scripts.phase5b_stage9c_expired_reclaim_scratch --execute` on the isolated `tcou` checkout at commit `cee8025`. Prior compile and offline suite: 412 PASS.

```text
OBSERVED: expired unstarted reservation blocks reclaim at 1296
PASS: reproduced and fenced expired-lease capacity deadlock
Battlelog requests: 0
PASS: exact scratch fixture cleanup
HARNESS EXIT CODE: 0
```

**Classification: confirmed behavioral defect, diagnostic PASS.** The production admission path does not reclaim an expired unstarted reservation when the 1,296/hour ceiling is filled, because `_usage` still charges the expired job and admission rejects the claim before reclaiming. This does **not** demonstrate an over-budget HTTP request; none was made. Harness-reported cleanup passed, but a separate independent read-only post-run table census has **not yet** been reported for this execution. Do not interpret exit code zero as successful reclamation. Stage 9C remains **HOLD** pending design and correction.

### Independent cleanup after expired-lease diagnostic

Operator ran the separate read-only scratch census following the full-ceiling expired-lease diagnostic. Each table returned **0**: `collectors`, `soldiers`, `collection_jobs`, `collection_events`, `stage9c_supervision_runs`. Output: `PASS: Independent expired-lease cleanup verification`. This verifies cleanup, **not** correct reclaim behavior. The deadlock remains reproduced; production Stage 9C remains HOLD.

### Independent post-run expired-lease cleanup

Operator independently verified that all five scratch tables contain zero rows: `collectors`, `soldiers`, `collection_jobs`, `collection_events`, `stage9c_supervision_runs`. Output: `PASS: Independent expired-lease cleanup verification`. The confirmed full-ceiling reclaim defect remains open; Stage 9C remains HOLD.

## Below-ceiling expired unstarted reservation reclaim — operator execution

On `tcou`, branch `test/stage9c-admission-concurrency` at `1648508`, the new scratch-only harness `scripts/phase5b_stage9c_reclaim_below_ceiling_scratch.py` compiled and the offline suite reported **412 passed**. Operator ran the harness with `--execute` against the isolated Stage 9C scratch database:

```text
PASS: expired unstarted lease reclaimed with fresh token
PASS: old token rejected for run, renew, finalize
PASS: reclaimed reservation counted once; final slot enforced
Battlelog requests: 0
PASS: exact scratch fixture cleanup
HARNESS EXIT CODE: 0
```

**Interpretation:** below the 1,296/hour ceiling, the production reclaim path advances the attempt, changes the lease token, rejects stale-token operations, and counts the new reservation once. This is a scoped PASS; it does not resolve the separately reproduced full-ceiling deadlock. The harness reports exact cleanup, but **independent post-run zero-row census is still pending** for this execution. Stage 9C remains HOLD.

### Independent cleanup after below-ceiling reclaim

Operator independently queried the isolated scratch database after the below-ceiling reclaim test. Counts were **0** for `collectors`, `soldiers`, `collection_jobs`, `collection_events`, and `stage9c_supervision_runs`; output: `PASS: Independent below-ceiling cleanup verification`. This closes the cleanup check for that execution. Full-ceiling expired unstarted reservation deadlock remains open; Stage 9C remains HOLD.

## Started-lease expiration and replacement — operator execution

On `tcou`, branch `test/stage9c-admission-concurrency` at `b396b94`, offline compilation succeeded and pytest reported **412 passed**. Operator ran `scripts/phase5b_stage9c_started_reclaim_scratch.py --execute` against the isolated scratch database:

```text
PASS: expired started attempt remains charged
PASS: replacement reservation separately charged; total 1296
PASS: stale owner fenced; further admission denied
Battlelog requests: 0
PASS: exact scratch fixture cleanup
HARNESS EXIT CODE: 0
```

**Interpretation:** a previously committed physical-start event remains charged after lease expiry, while the replacement attempt's reservation consumes a distinct slot. The aggregate reaches but does not exceed 1,296, and the previous lease token is fenced. Harness-reported cleanup passed; independent post-run five-table census is pending. This does not resolve the full-ceiling expired *unstarted* reservation deadlock. Production Stage 9C remains HOLD.

### Independent cleanup after started-lease reclaim

Operator independently queried the Stage 9C isolated scratch database after the started-lease reclaim harness. Counts were **0** for `collectors`, `soldiers`, `collection_jobs`, `collection_events`, and `stage9c_supervision_runs`; output: `PASS: Independent started-lease cleanup verification`. This closes the cleanup check for that execution. The full-ceiling expired-unstarted reservation deadlock remains unresolved. Stage 9C production trial remains HOLD.

## Full-ceiling expired-unstarted reservation correction — scratch execution

On `tcou`, branch `test/stage9c-admission-concurrency` at `68caea3`, Python compilation succeeded and the offline suite reported **412 passed**. The operator executed the revised `scripts/phase5b_stage9c_expired_reclaim_scratch.py --execute` against the isolated Stage 9C PostgreSQL scratch database:

```text
PASS: expired unstarted reservation releases capacity
PASS: reclaimed expired reservation at full ceiling
PASS: replacement token and attempt count advanced; total 1296
Battlelog requests: 0
PASS: exact scratch fixture cleanup
HARNESS EXIT CODE: 0
```

**Interpretation:** the candidate `_usage` lease-expiry filter permits reclaim of an expired unstarted reservation at the full 1,296-slot accounting boundary; the replacement attempt is charged and fenced. This is a scratch-only PASS, not production authorization. Harness-reported exact cleanup passed; **independent five-table zero-row verification is pending**, as are repeat claim-race/below-ceiling/started-lease regression checks and remaining Stage 9C gates. Production trial remains HOLD.

### Independent cleanup after full-ceiling reclaim fix

Operator independently queried the isolated Stage 9C scratch database after the full-ceiling reclaim correction harness. Counts were **0** for `collectors`, `soldiers`, `collection_jobs`, `collection_events`, and `stage9c_supervision_runs`; output: `PASS: Independent full-ceiling fix cleanup verification`. Cleanup is independently confirmed. Prior claim-race, below-ceiling reclaim, and started-lease reclaim scenarios still require reruns on the corrected code. Production Stage 9C remains HOLD.

## Claim-race regression after expired-reservation correction

Operator reran `scripts.phase5b_stage9c_claim_race_scratch --execute` on `tcou` after pulling corrected branch at `57a1108`:

```text
PASS: real production claim at 1295 reserves final slot
PASS: independent competing vehicles claim denied at 1296
PASS: committed reservation and lease ownership reconciled
Battlelog requests: 0
PASS: exact scratch fixture cleanup
HARNESS EXIT CODE: 0
```

This confirms the previously passing two-transaction final-slot race still passes with the expired-reservation accounting correction. **Independent five-table cleanup census remains pending** for this run. Below-ceiling and started-lease regressions remain pending. Stage 9C production trial remains HOLD.

### Independent cleanup after post-fix claim-race regression

Operator independently queried the isolated Stage 9C scratch database after the corrected-code claim-race regression. Counts were **0** for `collectors`, `soldiers`, `collection_jobs`, `collection_events`, and `stage9c_supervision_runs`; output: `PASS: Independent claim-race regression cleanup`. This closes the cleanup gate for the post-fix claim-race rerun. Below-ceiling and started-lease regression reruns remain pending. Stage 9C production trial remains HOLD.

## Below-ceiling reclaim regression after accounting correction

The first corrected-code rerun at `9693234` exited 1 on an obsolete harness expectation (`expired reservation unexpectedly disappeared`); its marker-owned cleanup reported PASS. Operator independently verified all five scratch tables were empty after that failed run. The harness assertion was updated in `58a3436` to expect expired unstarted reservations to release capacity. Operator pulled `58a3436`, compiled the harness, and reran:

```text
PASS: expired unstarted lease reclaimed with fresh token
PASS: old token rejected for run, renew, finalize
PASS: reclaimed reservation counted once; final slot enforced
Battlelog requests: 0
PASS: exact scratch fixture cleanup
HARNESS EXIT CODE: 0
```

The rerun PASSED. Independent five-table cleanup verification **after the successful rerun** is still pending. Started-lease regression remains pending. Stage 9C production trial remains HOLD.

### Independent cleanup after successful below-ceiling regression rerun

Operator independently verified **zero rows** in each of `collectors`, `soldiers`, `collection_jobs`, `collection_events`, and `stage9c_supervision_runs` after the successful `58a3436` below-ceiling regression rerun. Output: `PASS: Independent below-ceiling regression cleanup`. This closes its post-fix cleanup gate. Started-lease regression remains pending. Stage 9C production trial remains HOLD.

## Started-lease regression after expired-reservation accounting correction

Operator pulled branch at `7ebc30a` and reran `scripts.phase5b_stage9c_started_reclaim_scratch --execute` on isolated PostgreSQL scratch:

```text
PASS: expired started attempt remains charged
PASS: replacement reservation separately charged; total 1296
PASS: stale owner fenced; further admission denied
Battlelog requests: 0
PASS: exact scratch fixture cleanup
HARNESS EXIT CODE: 0
```

All four planned post-fix scratch scenarios have now passed their harnesses: full-ceiling expired-unstarted reclaim, two-transaction final-slot race, below-ceiling reclaim, and started-lease reclaim. **Independent five-table census for this final started-lease rerun is still pending.** Stage 9C production trial remains HOLD pending further failure-injection and cross-host validation.

### Independent cleanup after started-lease regression — regression group closed

Operator independently queried the isolated Stage 9C scratch database after the successful started-lease rerun: `collectors=0`, `soldiers=0`, `collection_jobs=0`, `collection_events=0`, `stage9c_supervision_runs=0`. Output: `PASS: Independent started-lease regression cleanup`.

**All four post-correction regression scenarios and their independent five-table cleanup censuses have passed.** This closes the expired-unstarted-reservation accounting defect's defined regression group, not the broader Stage 9C validation program. Remaining gates include rollback/failure injection, start-event durability, persistence failures, rolling-window boundaries, and cross-host tests. Production trial remains HOLD.

## FI-1 admission transaction rollback — first scratch execution

Operator pulled commit `95b2373` on `tcou` and ran `scripts.phase5b_stage9c_fi1_admission_rollback_scratch --execute` against the allowlisted Stage 9C scratch database. Reported output:

```text
PASS: rolled-back claim leaves no committed reservation or start event
PASS: independent collector reuses slot 1296; slot 1297 denied
Battlelog requests: 0
PASS: exact scratch fixture cleanup
HARNESS EXIT CODE: 0
```

**FI-1 harness PASS; independent five-table scratch cleanup census pending.** FI-2 and FI-3 have not yet executed. Stage 9C production trial remains HOLD.

### FI-1 independent cleanup — CLOSED

Operator independently verified zero rows in `collectors`, `soldiers`, `collection_jobs`, `collection_events`, and `stage9c_supervision_runs` after FI-1 PASS. Output: `PASS: Independent FI-1 rollback cleanup`. FI-1 harness and independent cleanup gates are both complete. FI-2 start-event failure and FI-3 post-start persistence rollback remain pending. Production Stage 9C HOLD.

### FI-2 start-event INSERT failure — CLOSED

Operator ran `scripts.phase5b_stage9c_fi2_start_failure_scratch --execute` on `tcou` (commit `9597d81`): injected production start-event INSERT failure propagated; HTTP was blocked (Battlelog requests 0); no committed start event; unexpired running reservation charged once; exact fixture and request-gate cleanup; harness exit 0. Independent follow-up census confirmed zero rows in `collectors`, `soldiers`, `collection_jobs`, `collection_events`, `stage9c_supervision_runs`, and zero `request_gates` rows matching `stage9c_fi2_start_failure-%`. `PASS: Independent FI-2 cleanup`. FI-2 closed. FI-3 pending; production HOLD.
