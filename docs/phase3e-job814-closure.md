# BF4PS Phase 3E job 814 abandoned-victim closure

Status: **COMPLETE — PASS**

Date: 2026-10-06 UTC

Parent validation plan: `docs/phase3e-lifecycle-validation-plan.md`

Current Alembic head: `0003_request_gates`

## Purpose

This closure resolves the intentionally abandoned victim checkpoint from the Phase 3E survivor-progress experiment without deleting, resetting, or manually rewriting the queue job. The abandoned work was required to recover through the production ownership and detailed-collection path so the original abrupt-loss evidence remained intact.

## Frozen victim

- job: **814**
- soldier: **390** (`ObiJuanQueHuevos`)
- persona: **1328461452**
- platform: **pc**
- resource/lane: `detailed` / `background`
- attempt-1 victim: `hnl-01` / `phase3e-hnl-01`
- attempt-1 collector UUID: `b2b3ef60-62e8-4d4a-91b0-41a2e2a3e001`
- attempt-1 lease token: `3d0cf2d7-22d1-4b4e-b9a4-b034cc048009`
- reclaimer: `kah-01` / `phase3e-kah-01`
- reclaimer UUID: `b2b3ef60-62e8-4d4a-91b0-41a2e2a3e002`

Attempt 1 was created by the survivor-progress victim harness. The victim performed no Battlelog request, lease renewal, clean release, or terminal finalization. The operator terminated the victim with `Ctrl-C`; its lease expired naturally. While job 814 remained abandoned, kah-01 successfully completed unrelated jobs 815 and 816 as durable events 812 and 813, proving survivor progress was not stalled by the dead owner.

## Closure safety contract

The dedicated closure harness `scripts/phase3e_closure_victim_finalize.py` was restricted to the existing test target and production ownership model. It required:

- execution on `kah-01`;
- the expected Phase 3E test database/Alembic target through the shared `assert_target` guard;
- job 814 to still be soldier 390, `detailed`, `background`, `running`, attempt 1;
- the attempt-1 owner to still be the frozen hnl-01 UUID;
- a complete attempt-1 ownership tuple with an expired lease;
- no pre-existing terminal event for job 814;
- the reclaimer collector to be enabled and undrained;
- the production detailed collector to be restricted to soldier 390;
- a hard total attempt ceiling of 2;
- at most one authorized Battlelog request.

No administrative job deletion, queue reset, replacement job, substitute soldier, direct persistence shortcut, or fabricated terminal history was authorized.

## Observed production-path recovery

The closure harness observed the exact abandoned attempt-1 owner and token, confirmed lease expiration, and allowed kah-01 to reclaim the same logical job through the production detailed collector path.

The run completed successfully:

- Battlelog request budget: at most **1**;
- job 814 reclaimed cross-host by kah-01;
- attempt count advanced **1 -> 2**;
- lease token rotated away from the obsolete hnl-01 token;
- Battlelog returned HTTP **200**;
- detailed normalization/persistence succeeded;
- `history_appended=True`;
- queue row finalized and disappeared;
- `collection_state.detailed_state` converged to `success`;
- a `detailed_stats_current` row persisted for soldier 390;
- kah-01 released `current_job_id` after finalization.

The durable terminal result is:

| Event | Job | Soldier | Attempt | Collector | HTTP | Result |
|---:|---:|---:|---:|---|---:|---|
| **814** | **814** | **390** | **2** | `phase3e-kah-01` | **200** | `collection_success` |

The harness reported:

- `cross-host reclamation: PASS`
- `attempt increment 1 -> 2: PASS`
- `lease-token rotation: PASS`
- `queue finalization: PASS`
- `detailed state/current persistence: PASS`
- `reclaimer cleanly released current job: PASS`
- `PHASE 3E ABANDONED-VICTIM CLOSURE: PASS`

## Evidence interpretation

Job 814 now provides a second abrupt-loss recovery shape complementary to Lifecycle B job 813.

Lifecycle B deliberately inserted an intermediate attempt-2 reclaim/fencing checkpoint before controlled attempt-3 completion. Job 814 instead demonstrates the simpler natural path: attempt 1 dies abruptly, unrelated work continues elsewhere, the expired job is later reclaimed directly as attempt 2 by another physical collector, and that same production attempt completes successfully.

The attempt-1 abrupt-loss evidence is not erased by successful closure. No attempt-1 terminal event was invented after the fact. Durable event 814 records only the successful attempt-2 terminal collection.

## Remaining Phase 3E closure work

The abandoned queue checkpoint itself is now resolved. The remaining acceptance item is to prove final clean-stop/convergence for the three Phase 3E collector identities.

That proof must distinguish queue ownership from collector-registry liveness bookkeeping. In particular, the former hnl-01 victim registry may still contain stale `current_job_id` state from the process that died abruptly. Final closure should use the normal collector registration/heartbeat/stop primitives rather than direct SQL cleanup, then verify:

- all three stable identities remain exact and unretired;
- no collector owns a current job;
- clean-stop state is recorded for all three collectors;
- no Phase 3E closure queue work remains;
- operator-owned `enabled` / `drained` controls are not silently overwritten.

Only after that evidence is captured should the final Phase 3E acceptance audit report complete PASS.
