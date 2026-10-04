# Phase 1 Detailed Persistence — Live Validation

This note records the live PostgreSQL validation of the Phase 1 atomic detailed-statistics success path. It supplements `docs/phase1-detailed-collector.md` and does not replace that frozen implementation contract.

## Environment

Validation was run on `tcou` against `bf4_playerstats_test`. The harness refuses to run when the connected database name does not contain `test`.

The test subject was the existing Patient Zero soldier:

- player: `mauirixxx`
- persona ID: `236753552`
- platform: `pc`

No Battlelog request was made by this validation. Synthetic normalized values matching the 48-field Detailed Stats Retention Contract were used so the database transaction boundary could be tested independently from HTTP/source behavior.

## Harness

`scripts/phase1_persistence_integration.py` exercises `persist_detailed_success()` through real PostgreSQL transactions and temporary registered collectors/jobs. Test-owned rows are removed at the end of a successful run.

## Observed result

The live run completed with:

```text
===== BF4PS PHASE 1 PERSISTENCE INTEGRATION =====
database:   bf4_playerstats_test
soldier:    mauirixxx (236753552, pc)
first success:              PASS (current=1 history=1 event=1 job=0)
identical success:          PASS (history unchanged)
changed success:            PASS (history appended)
collection state:           PASS
expired lease rejection:    PASS (no success writes committed)
cleanup:                    PASS

PHASE 1 PERSISTENCE INTEGRATION: PASS
```

The repository unit suite also passed immediately before this live validation: 23 tests passed.

## Contract demonstrated

The test established the following behavior against the real BF4PS PostgreSQL schema:

1. A first successful detailed collection creates/updates `detailed_stats_current`, appends the first `detailed_stats_history` snapshot, writes a success event, updates collection state, and removes the owned actionable job.
2. Repeating an identical retained payload refreshes current success state without appending a duplicate history snapshot.
3. Changing a retained statistic appends exactly one additional history snapshot.
4. Successful persistence leaves the detailed collection state at `success` with zero consecutive failures.
5. A deliberately expired lease is rejected before success persistence. No current/history/event success writes from the stale owner are committed, and its queue row remains recoverable.
6. The harness cleans up its temporary collectors, jobs, events, and synthetic detailed-stat rows after validation.

## Significance

This validates the Phase 1 atomic-success and fencing boundary independently of Battlelog. In particular, it demonstrates that a stale collector cannot commit authoritative success data after losing lease ownership.

The next Phase 1 implementation step is the collector orchestration path that joins the already-tested pieces: queue claim, transition to running, database-coordinated Battlelog request pacing, detailed fetch, normalization, atomic persistence, and classified failure/retry handling.

This validation does **not** satisfy the complete Phase 1 acceptance gate by itself. Live end-to-end Battlelog collection, request-gate behavior, retry/failure behavior, the multi-platform validation cohort, and the remaining acceptance items in `docs/phase1-detailed-collector.md` still require validation before bootstrap or distributed deployment.