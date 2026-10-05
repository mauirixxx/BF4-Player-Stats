# BF4PS Phase 3E lifecycle validation plan

Status: **LIFECYCLE A COMPLETE — PASS; LIFECYCLE B NEXT**

Date: 2026-10-05 UTC

Frozen parent design: `docs/phase3e-distributed-endurance-design.md`

Completed endurance evidence: `docs/phase3e-third-endurance-run.md`

Current Alembic head: `0003_request_gates`

## Purpose

The three-host endurance portion of Phase 3E is complete. Round Three reconciled 120/120 successful attempts and closed the bounded-feeder concurrency defect discovered in Round Two.

Lifecycle A has now fully exercised graceful drain/rejoin behavior under a sustained 360-soldier workload and subsequent natural retry convergence. The primary lifecycle reconciliation passed against the observed durable drain acknowledgement boundary. Eight transient `battlelog_normalization` failures were preserved as retryable work, all eight later normalized successfully under a read-only forensic probe, and all eight then succeeded through the normal production retry path on attempt two. Final retry reconciliation passed with no residual queue, no third-or-later attempts, no foreign retry work, successful detailed collection state, and persisted detailed current rows for all eight retry soldiers.

- **Lifecycle A: COMPLETE/PASS** — graceful drain, continued drained state, explicit undrain, safe rejoin, and natural retry convergence.
- **Lifecycle B: NEXT** — abrupt owner loss, lease expiration, cross-host reclamation, stale-owner fencing.

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

# Lifecycle A — graceful drain/rejoin — COMPLETE/PASS

## Frozen workload contract

Lifecycle A used exactly **360 fresh pristine soldiers**: 120 PC, 120 PS4, and 120 Xbox One. The primary run had a hard ceiling of 360 terminal attempts and used the production bounded feeder at target depth 6 rather than materializing all jobs at once.

The target collector was `hnl-01`.

## Executed choreography and durable boundaries

The three collectors were started against the frozen workload and all made useful progress. `hnl-01` was persistently drained while work remained. The operator drain event was recorded at event ID **642**. The worker then observed the persistent drain and emitted the effective acknowledgement boundary at event ID **643**. One target terminal event occurred between the operator mutation and worker acknowledgement; reconciliation correctly treats this as bounded pre-ack in-flight work rather than forbidden post-drain ownership.

While the target remained drained, `kah-01` and `tcou` continued useful work. The target later observed explicit undrain at event ID **736** and resumed useful collection under the same stable UUID.

The primary run reached exactly 360 terminal attempts distributed as:

- `hnl-01`: 90
- `kah-01`: 135
- `tcou`: 135

Primary reconciliation passed all lifecycle ownership properties using drain operator boundary 642, drain acknowledgement boundary 643, and undrain boundary 736. The run contained eight terminal `battlelog_normalization` failures. Those jobs were correctly released to retryable `pending` state with attempt count 1 and no lingering owner/lease; the residual queue exactly matched those failures.

## Normalization forensics

The eight residual jobs were:

`765, 766, 768, 769, 770, 771, 772, 773`.

Their soldiers were:

`8693, 8694, 8696, 8697, 8698, 8699, 8700, 8701`.

A dedicated diagnostic bypassed queue claiming/finalization and directly re-fetched only those eight identities using the production Battlelog detailed fetcher and production normalizer. Requests retained conservative five-second spacing. All eight later returned structurally valid PS4 payloads and normalized successfully with all 48 retained detailed fields populated.

The diagnostic verified that the target `collection_jobs`, target `collection_state`, and target `collection_events` accounting were unchanged by the probe. The evidence supports treating the original normalization results as transient source-response failures rather than permanently invalid soldiers or manual-cleanup residue.

The original malformed/transient Battlelog responses were not retained, so their exact payload defect cannot be reconstructed after the fact. Future diagnostics should preserve sufficiently bounded failure detail at collection time if distinguishing transient payload shapes becomes operationally important; full Battlelog payload retention is still not authorized.

## Primary-run PASS properties

The primary lifecycle run produced durable evidence for:

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

## Retry convergence execution

The retry-convergence harness authorized only jobs `765, 766, 768, 769, 770, 771, 772, 773` and used the normal production claim, request-gate, detailed-fetch, normalization, persistence, failure, and finalization paths on `tcou` under its stable collector identity.

The first retry invocation successfully completed job 765 / soldier 8693, then the test harness itself stopped because its safety check incorrectly required all eight residual rows to remain present after every successful finalization. This was a harness invariant bug, not a production queue/persistence failure. The harness was corrected to permit already-authorized jobs to disappear naturally from the queue after successful finalization.

The resumed invocation then processed the remaining seven authorized jobs successfully. No manual queue reset, deletion, replacement job, substitute soldier, or state cleanup was used.

The resulting attempt-two success event span was **803..810**:

| Event | Job | Soldier | Result |
|---:|---:|---:|---|
| 803 | 765 | 8693 | `collection_success` |
| 804 | 766 | 8694 | `collection_success` |
| 805 | 768 | 8696 | `collection_success` |
| 806 | 769 | 8697 | `collection_success` |
| 807 | 770 | 8698 | `collection_success` |
| 808 | 771 | 8699 | `collection_success` |
| 809 | 772 | 8700 | `collection_success` |
| 810 | 773 | 8701 | `collection_success` |

## Final retry reconciliation — PASS

The dedicated read-only reconciliation reported:

- attempt-two terminal events: **8/8**;
- residual authorized queue: **0**;
- third-or-later terminal attempts: **0**;
- foreign retry work: **0**;
- exact retry jobs and soldiers covered: **PASS**;
- all retries remained PS4: **PASS**;
- retry collector identity exact: **PASS**;
- no HTTP/throttle/error evidence on retries: **PASS**;
- authorized retry queue fully converged: **PASS**;
- all eight collection-state rows present: **PASS**;
- all eight retry soldiers `detailed_state=success`: **PASS**;
- all eight retry soldiers have persisted `detailed_stats_current` rows: **PASS**.

The reconciliation itself performed zero database writes and zero Battlelog requests.

## Lifecycle A conclusion

**Lifecycle A is closed PASS.**

The experiment demonstrated graceful persistent drain, a durable worker acknowledgement boundary, continued survivor progress, explicit undrain/rejoin under the same stable physical identity, safe queue ownership, natural retry preservation after transient source failures, restartable retry execution after a harness-side interruption, and complete retry convergence without manual database cleanup.

# Lifecycle B — abrupt owner loss/reclamation/fencing — NEXT

Lifecycle B remains required and is intentionally separate from Lifecycle A. Lifecycle A is now sufficiently closed to begin its implementation.

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

Before writing or modifying schema-dependent code, consult `docs/database-schema-reference.md` and the complete current Alembic migration chain. `docs/database-schema-reference.md` is the repository's human-readable reference for the current Alembic head; the migrations remain the executable source of truth. If documentation and migrations disagree, stop and reconcile them before implementation. Schema changes must update the schema reference in the same change set.

## Next implementation step

Design and build the bounded Lifecycle B harness for abrupt owner loss, lease expiration, cross-host reclamation, and stale-owner fencing. Freeze its exact workload, lease timing, owner/reclaimer identities, kill boundary, expected event sequence, and reconciliation criteria before executing the destructive portion of the experiment.
