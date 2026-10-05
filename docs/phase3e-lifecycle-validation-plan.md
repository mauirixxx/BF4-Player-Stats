# BF4PS Phase 3E lifecycle validation plan

Status: **LIFECYCLE A PRIMARY RUN PASSED — RETRY CONVERGENCE PENDING**

Date: 2026-10-04 UTC

Frozen parent design: `docs/phase3e-distributed-endurance-design.md`

Completed endurance evidence: `docs/phase3e-third-endurance-run.md`

Current Alembic head: `0003_request_gates`

## Purpose

The three-host endurance portion of Phase 3E is complete. Round Three reconciled 120/120 successful attempts and closed the bounded-feeder concurrency defect discovered in Round Two.

Lifecycle A has now exercised graceful drain/rejoin behavior under a sustained 360-soldier workload. The primary lifecycle reconciliation passes when evaluated against the observed durable drain acknowledgement boundary. Eight source/normalization failures remain as legitimate retryable queue work; direct read-only forensic re-fetches later normalized successfully for all eight. Lifecycle A therefore still needs a bounded retry/convergence closure before Lifecycle B begins.

- **Lifecycle A:** graceful drain, restart/continued drained state, explicit undrain, safe rejoin, then retry convergence.
- **Lifecycle B:** abrupt owner loss, lease expiration, cross-host reclamation, stale-owner fencing.

## Safety boundary shared by both experiments

All lifecycle validation remains restricted to:

- database: `bf4_playerstats_test`
- PostgreSQL target: `mak-db-02.bf4statusbot.com`
- resource: `detailed`
- lane: `background`
- explicit fresh frozen cohort only
- bounded feeder only
- explicit hard global attempt ceiling for the primary lifecycle pass
- conservative per-egress pacing

No full-population bootstrap is authorized. No production BF4PS database is authorized. No intentional Battlelog throttle experiment is authorized.

Every harness must refuse to run if the database target, Alembic head, frozen cohort, or expected collector identity does not match its frozen configuration.

## Stable physical identities

| Physical host | Collector | Stable UUID | Egress key |
|---|---|---|---|
| `hnl-01` | `phase3e-hnl-01` | `b2b3ef60-62e8-4d4a-91b0-41a2e2a3e001` | `phase3e-hnl-01` |
| `kah-01` | `phase3e-kah-01` | `b2b3ef60-62e8-4d4a-91b0-41a2e2a3e002` | `phase3e-kah-01` |
| `tcou` | `phase3e-tcou` | `b2b3ef60-62e8-4d4a-91b0-41a2e2a3e003` | `phase3e-tcou` |

Stable collector identity must survive restart. Persistent operator controls must not be silently reset by registration or startup.

# Lifecycle A — graceful drain/rejoin

## Frozen workload contract

Lifecycle A uses exactly **360 fresh pristine soldiers**: 120 PC, 120 PS4, and 120 Xbox One. The primary run has a hard ceiling of 360 terminal attempts and uses the production bounded feeder at target depth 6 rather than materializing all jobs at once.

The target collector is `hnl-01`.

## Executed choreography and durable boundaries

The three collectors were started against the frozen workload and all made useful progress. `hnl-01` was persistently drained while work remained. The operator drain event was recorded at event ID **642**. The worker then observed the persistent drain and emitted the effective acknowledgement boundary at event ID **643**. One target terminal event occurred between the operator mutation and worker acknowledgement; reconciliation treats this as bounded pre-ack in-flight work rather than forbidden post-drain ownership.

While the target remained drained, `kah-01` and `tcou` continued useful work. The target later observed explicit undrain at event ID **736** and resumed useful collection under the same stable UUID.

The primary run reached exactly 360 terminal attempts distributed as:

- `hnl-01`: 90
- `kah-01`: 135
- `tcou`: 135

Primary reconciliation passed all lifecycle ownership properties when using drain operator boundary 642, drain acknowledgement boundary 643, and undrain boundary 736. The run contained eight terminal `battlelog_normalization` failures. Those jobs were correctly released to retryable `pending` state with attempt count 1 and no lingering owner/lease; the residual queue exactly matched those failures.

## Normalization forensics

The eight residual jobs are:

`765, 766, 768, 769, 770, 771, 772, 773`.

A dedicated diagnostic bypassed queue claiming/finalization and directly re-fetched only those eight identities using the production Battlelog detailed fetcher and production normalizer. Requests retained the conservative five-second spacing. All eight later returned structurally valid PS4 payloads and normalized successfully with all 48 retained detailed fields populated.

The diagnostic verified that the target `collection_jobs`, target `collection_state`, and target `collection_events` accounting were unchanged by the probe. The evidence therefore supports treating the original normalization results as transient source-response failures rather than permanently invalid soldiers or manual-cleanup residue.

The original malformed/transient Battlelog responses were not retained, so their exact payload defect cannot be reconstructed after the fact. Future diagnostics should preserve sufficiently bounded failure detail at collection time if distinguishing transient payload shapes becomes operationally important; full Battlelog payload retention is still not authorized.

## Lifecycle A primary-run PASS properties

The primary lifecycle run now has durable evidence for:

- exactly 360 terminal attempts across the frozen cohort;
- each frozen soldier attempted exactly once in the primary pass;
- all three collectors progressed;
- drain acknowledgement was bounded;
- target remained quiet after drain acknowledgement;
- survivor collectors progressed while target was drained;
- target progressed again after explicit undrain;
- event identity snapshots matched the frozen physical identities;
- no frozen-collector work escaped the cohort during the run;
- residual queue exactly matched the eight retryable failures;
- collectors owned no current job at reconciliation.

The eight retryable failures do **not** invalidate the graceful lifecycle proof. They do mean final queue/state convergence is not yet complete.

## Lifecycle A next step — bounded retry convergence

Do not manually delete, reset, or replace the eight residual jobs. They are naturally occurring retry evidence.

Build and execute a narrowly bounded retry-convergence harness that:

1. authorizes only the eight residual job IDs and their frozen soldiers;
2. uses the normal production claim, request-gate, detailed-fetch, normalization, persistence, failure, and finalization paths;
3. preserves normal five-second per-egress pacing;
4. permits only the already-created retryable jobs — no new cohort expansion or substitute soldiers;
5. requires attempt number 2 for the retry attempt;
6. stops immediately if work escapes the eight-job residual set;
7. reconciles event history, queue state, `collection_state`, and persisted detailed current/history state after the retry pass;
8. records whether each job succeeds or remains legitimately retryable.

Expected successful closure is eight second-attempt successes, an empty Lifecycle A residual queue, successful detailed state for all 360 frozen soldiers, and no ownership/accounting divergence. If any of the eight fails again, preserve it and investigate the new durable error evidence rather than forcing cleanup.

# Lifecycle B — abrupt owner loss/reclamation/fencing

Lifecycle B remains required and is intentionally not combined with Lifecycle A. Begin its implementation only after Lifecycle A retry convergence is reconciled.

Its frozen parent requirements are:

1. arrange one bounded test job to be owned under a deliberately short test lease;
2. terminate that owner without graceful release/finalization;
3. prove survivors continue unrelated work;
4. wait for lease expiration;
5. require a different physical collector to reclaim the same logical job;
6. prove attempt number increments and lease token rotates;
7. attempt stale-owner mark-running, renew, release, and finalize mutations using the former ownership tuple and require rejection;
8. allow only the current owner to finalize normally;
9. reconcile the complete durable ownership/event history.

The short lease is test-only and must not redefine normal production lease duration.

## Implementation rule

Lifecycle harnesses must use production collector/queue ownership APIs wherever the behavior under test is a production invariant. Direct SQL is acceptable for read-only validation and explicit operator-control setup only where the production design defines that field as persistent operator state. Harnesses must not invent a second scheduler, ownership model, or cleanup path.

Before writing or modifying schema-dependent code, consult `docs/database-schema.md` and the complete current Alembic migration chain. `docs/database-schema.md` is the repository's current schema-reference document; do not invent or rely on a nonexistent `docs/database-schema-reference.md`. If documentation and migrations disagree, stop and reconcile them before implementation. Schema changes must update the schema document in the same change set.

## Next implementation step

Build the bounded eight-job Lifecycle A retry-convergence harness and its read-only reconciliation. Do not proceed to Lifecycle B until that evidence is closed.