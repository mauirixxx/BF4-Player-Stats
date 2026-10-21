# BF4PS Phase 3E lifecycle validation plan

Status: **LIFECYCLE A COMPLETE — PASS; LIFECYCLE B COMPLETE — PASS; FINAL CLEAN-STOP CLOSURE REMAINS**

Date: 2026-10-05 UTC

Frozen parent design: `docs/phase3e-distributed-endurance-design.md`

Completed endurance evidence: `docs/phase3e-third-endurance-run.md`

Current Alembic head: `0003_request_gates`

## Purpose

The three-host endurance portion of Phase 3E is complete. Round Three reconciled 120/120 successful attempts and closed the bounded-feeder concurrency defect discovered in Round Two.

Lifecycle A fully exercised graceful drain/rejoin behavior under a sustained 360-soldier workload and subsequent natural retry convergence. Lifecycle B then exercised abrupt owner loss, expired-lease cross-host reclamation, lease-token rotation, stale-owner fencing, and successful production-path completion by the surviving owner.

Dedicated closure probes subsequently proved persistent drain across restart/heartbeat, explicit undrain/rejoin, and unrelated survivor progress while a victim job remained abandoned after abrupt owner loss.

At this point the only remaining Phase 3E acceptance item is the final clean-stop/convergence closure after preserving the abandoned victim checkpoint.

## Safety boundary shared by both experiments

All lifecycle validation remained restricted to:

- database: `bf4_playerstats_test`
- PostgreSQL target: `mak-db-02.bf4statusbot.com`
- resource: `detailed`
- lane: `background`
- explicit fresh frozen cohort only
- bounded feeder/work only
- explicit hard attempt ceilings
- conservative per-egress pacing

No full-population bootstrap was authorized. No production BF4PS database was authorized. No intentional Battlelog throttle experiment was authorized.

Every harness was required to refuse to run if the database target, Alembic head, frozen cohort, or expected collector identity did not match its frozen configuration.

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

# Lifecycle B — abrupt owner loss/reclamation/fencing — COMPLETE/PASS

## Frozen contract

Lifecycle B deliberately used one pristine PC soldier and one detailed/background queue job so that ownership transitions could be observed without unrelated queue activity obscuring the experiment.

Frozen workload:

- soldier: **389** (`niteraat`)
- persona: **1309609549**
- platform: **pc**
- job: **813**
- victim: `hnl-01` / `phase3e-hnl-01`
- reclaimer: `kah-01` / `phase3e-kah-01`
- test lease: **30 seconds** for the abrupt-loss/reclaim checkpoints

The short lease was test-only and does not redefine normal production lease duration.

## Executed ownership choreography

### Attempt 1 — abrupt victim loss

`hnl-01` claimed job 813 as attempt 1 under lease token:

`9ad8057a-57fe-4cdb-82fa-49fc58c4ea39`

The victim harness intentionally performed no Battlelog request, no lease renewal, and no clean release. Once armed, the operator terminated it with `Ctrl-C`, producing an actual abrupt process loss while the database still contained the ownership tuple. The 30-second lease then expired naturally.

### Attempt 2 — cross-host reclamation checkpoint

After expiration, `kah-01` reclaimed the same logical job as attempt 2 under a new lease token:

`d912e36b-902f-4b5a-bb52-36576c5d6892`

The reclaim checkpoint verified:

- stale attempt: **1**;
- stale owner: `hnl-01` stable collector UUID;
- new attempt: **2**;
- new owner: `kah-01` stable collector UUID;
- lease token rotated;
- no Battlelog request was required to prove reclamation.

Attempt 2 was deliberately left as an ownership/fencing checkpoint rather than being finalized. Its lease was allowed to expire before the controlled production-path completion. This means the durable terminal event ledger does not contain attempt-1 or attempt-2 terminal events; those attempts are ownership transitions established by the harness/operator evidence, not fabricated terminal history.

### Stale-owner fencing — PASS

With attempt 2 owned by `kah-01`, the former attempt-1 `hnl-01` ownership tuple was replayed against all four ownership-sensitive mutations. Every stale mutation was rejected:

- `mark_job_running` — **REJECTED**;
- `renew_lease` — **REJECTED**;
- `release_for_retry` — **REJECTED**;
- `finalize_owned_job` — **REJECTED**.

The probe verified that the queue row was unchanged both inside the transaction and after rollback. It persisted zero database writes and made zero Battlelog requests.

This directly proves that possession of an obsolete collector UUID plus obsolete lease token cannot mutate a job after another owner has reclaimed it.

### Attempt 3 — controlled production-path completion

After the deliberately retained attempt-2 lease expired, `kah-01` reclaimed job 813 again through the production detailed collector path. The claim became attempt 3 and rotated the lease token again to:

`5a02a116-ecd9-4ab2-b5c5-4518ef84bc1b`

Only soldier 389 was authorized and at most one Battlelog request was permitted. The normal request gate, Battlelog detailed fetcher, normalizer, persistence path, collection-state update, event ledger, and queue finalization were used.

The request returned HTTP **200** and produced durable event **811**:

| Event | Job | Soldier | Attempt | Collector | Result |
|---:|---:|---:|---:|---|---|
| 811 | 813 | 389 | 3 | `phase3e-kah-01` | `collection_success` |

The completion also reported `history_appended=True`, finalized the queue row, and persisted successful detailed current/state data.

## Final read-only reconciliation — PASS

The dedicated final reconciliation observed one durable ledger event for job 813: event 811, `collection_success`, attempt 3, owned by `phase3e-kah-01` with the attempt-3 lease token.

It passed every final invariant:

- Lifecycle B queue job fully finalized;
- exactly one successful collection event;
- success is durable event 811;
- success occurred only on attempt 3;
- success owned by the `kah-01` stable collector identity;
- success used the rotated attempt-3 lease token and neither obsolete token;
- soldier/persona/platform/resource/lane identity exact;
- result `success`, HTTP 200, no error class;
- `collection_state.detailed_state` converged to `success` with a successful timestamp, zero consecutive failures, and no detailed error;
- `detailed_stats_current` row persisted;
- at least one `detailed_stats_history` snapshot persisted;
- victim and reclaimer stable collector identities remained exact;
- neither lifecycle collector retained `current_job_id` ownership.

The final reconciliation performed zero database writes and zero Battlelog requests.

## Lifecycle B conclusion

**Lifecycle B is closed PASS.**

The experiment demonstrated that abrupt process loss does not require a clean release for recovery; an expired lease permits a different physical collector to reclaim the same logical job; reclamation increments the attempt number and rotates the lease token; an obsolete owner/token tuple is fenced from mark-running, renewal, retry release, and finalization; and a surviving collector can subsequently reclaim and complete the job through the normal production detailed-collection path with correct persistence and queue convergence.

The observed three-attempt sequence is intentionally preserved exactly as executed. Attempt 2 was a controlled reclaim/fencing checkpoint whose lease was allowed to expire; it is not rewritten as a terminal collection attempt after the fact.

# Phase 3E closure evidence

## Bounded feeder acceptance criterion — PASS from Round Three evidence

The first closure audit incorrectly phrased this requirement as `bounded feeder target depth <= 6 throughout run`. That is **not** the frozen Phase 3E requirement and contradicts the already-documented Round Three concurrency result.

The frozen design requires that queue **replenishment remain bounded throughout the run**. Target depth 6 is a replenishment target, not an instantaneous distributed queue-depth invariant. Round Three exists specifically because Round Two demonstrated that concurrent feeders can transiently observe actionable depth 7 while the target is 6.

Round Three captured live worker telemetry from all three physical collectors:

| Host | Local attempts | Max actionable observed | Stop |
|---|---:|---:|---|
| `tcou` | 40 | 6 | clean |
| `hnl-01` | 40 | 7 | clean |
| `kah-01` | 40 | 6 | clean |

`hnl-01` explicitly emitted `NOTICE: transient actionable depth observed above feeder target: 7 > 6`, did not abort, and continued through its 40th local attempt. Global reconciliation then proved exactly 120 terminal attempts, 120 unique soldiers, 120 unique logical jobs, zero failures, zero throttle signals, an empty finalized Round Three queue, preserved controls, all three request gates, and clean stops for all three collectors.

Therefore the correct frozen property — **bounded replenishment under concurrent feeders** — is already proven by the preserved Round Three run evidence. No additional feeder closure experiment is required. The acceptance audit has been corrected to represent the frozen design rather than the erroneous `<= 6` interpretation.

## Persistent drain survives restart — PASS

`hnl-01` was explicitly drained and then exercised through a restart-style registration/heartbeat/clean-stop probe under the same stable collector UUID. The probe demonstrated that:

- persistent `drained=true` existed before restart;
- stable-identity registration did not clear the drain;
- registration remained claim-blocked;
- heartbeat did not clear the drain and remained claim-blocked;
- the restarted probe acquired no `current_job_id`;
- clean stop preserved the operator drain and left no current job.

The operator then explicitly undrained `hnl-01`. A dedicated rejoin probe demonstrated that registration and heartbeat preserved `drained=false`, the collector became claim-eligible again, no work was accidentally claimed by the probe, and clean stop preserved the explicit undrain.

This closes both the restart-while-drained requirement and the associated persistent-control overwrite concern for the exercised registration/heartbeat/stop path.

## Abrupt loss with unrelated survivor progress — PASS

A separate three-job closure cohort was frozen after the candidate census identified genuinely pristine `never_attempted` PC soldiers:

| Job | Soldier | Name | Role |
|---:|---:|---|---|
| 814 | 390 | `ObiJuanQueHuevos` | abrupt-loss victim |
| 815 | 391 | `ASussyBaka` | survivor work |
| 816 | 392 | `Exospax` | survivor work |

`hnl-01` claimed job 814 / soldier 390 as attempt 1 with lease token `3d0cf2d7-22d1-4b4e-b9a4-b034cc048009`. The claim started at `2026-10-05 20:58:25.133293+00:00` and its test lease expired at `20:58:55.133293+00:00`. The victim performed no Battlelog request, lease renewal, clean release, or terminal finalization. The operator then terminated the victim with `Ctrl-C`.

Immediately before termination, jobs 815 and 816 remained pristine pending attempt-zero jobs. The survivor harness on `kah-01` was explicitly restricted to survivor soldiers 391/392 so it could not reclaim victim job 814.

### Harness checkpoint after first survivor

The first survivor invocation successfully completed job 815 / soldier 391 through the production detailed collector path and appended history. The harness then stopped before job 816 because it supplied `allowed_soldier_ids=(391,392)` with `max_total_attempts=1`. The queue primitive correctly treats that ceiling as a total bounded-attempt ceiling across the supplied cohort, so event 812 consumed the single permitted attempt and the second claim returned `None`.

This was a harness-bounds mistake, not a production queue or collection failure. No reset, reseed, deletion, or manual database cleanup was performed.

The harness was changed to be checkpoint-aware. It recognized finalized job 815 from its exact durable success event, recognized job 816 as the only pristine pending survivor, and bounded the resumed production collector to soldier 392 alone with a one-attempt ceiling.

The resumed invocation completed job 816 successfully. Final survivor evidence is:

| Event | Job | Soldier | Attempt | Collector | HTTP | Result |
|---:|---:|---:|---:|---|---:|---|
| 812 | 815 | 391 | 1 | `phase3e-kah-01` | 200 | `collection_success` |
| 813 | 816 | 392 | 1 | `phase3e-kah-01` | 200 | `collection_success` |

Both successes reported `history_appended=True`. Both survivor queue rows finalized, both `collection_state.detailed_state` values converged to `success`, and both detailed current rows persisted.

Most importantly, the harness compared the full selected queue ownership shape for victim job 814 before and after survivor collection and reported:

`victim job unchanged while survivors progressed: PASS`

Therefore an abrupt owner loss holding one job did not stall unrelated useful work by a surviving physical collector. The evidence also demonstrates safe resume after a harness-side interruption without discarding the first valid survivor result.

## Remaining closure requirement

Only one frozen acceptance requirement remains unresolved:

- **all collectors stop cleanly after the experiment**.

The current database intentionally retains victim job 814 as the abandoned attempt-1 checkpoint from the survivor-progress proof. That state must be preserved until the final closure choreography explicitly resolves the abandoned job and verifies the collector registry/queue are clean. Registry idle/current-job state alone is not sufficient evidence.

# Phase 3E lifecycle validation conclusion

**Lifecycle A and Lifecycle B are COMPLETE/PASS. Bounded feeder behavior, persistent drained restart/rejoin, and unrelated survivor progress after abrupt owner loss are also proven. Final clean-stop/convergence closure is the sole remaining Phase 3E acceptance item.**

Together, the evidence now covers:

- sustained concurrent bounded-feeder operation with target 6 and a safe transient observation of 7;
- graceful administrative drain and rejoin under stable identity;
- persistent drain surviving registration/heartbeat restart behavior;
- explicit undrain restoring claim eligibility without silent control overwrite;
- continued useful work by surviving collectors;
- natural retry convergence after transient source failures;
- abrupt owner death without graceful cleanup;
- unrelated survivor work progressing while the victim job remains abandoned;
- expired-lease cross-host reclamation;
- monotonically increasing attempt ownership with lease-token rotation;
- stale-owner fencing after reclamation;
- successful current-owner production-path completion;
- converged queue and detailed persistence state.

## Implementation rule retained for future Phase 3E work

Lifecycle/endurance harnesses must use production collector/queue ownership APIs wherever the behavior under test is a production invariant. Direct SQL is acceptable for read-only validation and explicit operator-control setup only where the production design defines that field as persistent operator state. Harnesses must not invent a second scheduler, ownership model, or cleanup path.

Before writing or modifying schema-dependent code, consult `docs/database-schema-reference.md` and the complete current Alembic migration chain. `docs/database-schema-reference.md` is the repository's human-readable reference for the current Alembic head; the migrations remain the executable source of truth. If documentation and migrations disagree, stop and reconcile them before implementation. Schema changes must update the schema reference in the same change set.

## Next step

Perform the final clean-stop/convergence closure without erasing the already-preserved abrupt-loss evidence. Resolve abandoned victim job 814 through the production ownership model, leave all Phase 3E collectors with no current job, stop the final closure process cleanly, and rerun final acceptance. Any cleanup must preserve the historical evidence already recorded above.
