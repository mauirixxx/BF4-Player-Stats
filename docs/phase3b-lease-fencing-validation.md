# BF4PS Phase 3B lease fencing validation

Status: **PASS — live test-database integration evidence**

Date: 2026-10-04 UTC

Phase 3 design reference: `docs/phase3-distributed-collector-design.md`

Current Alembic head: `0003_request_gates`

## Purpose

Preserve the deterministic Phase 3B proof that an expired BF4PS queue lease can be reclaimed by another collector and that the superseded collector's stale ownership tuple cannot mutate the reclaimed job.

Harness: `scripts/phase3b_lease_fencing_integration.py`

No Battlelog request was performed.

## Test boundary

- database: `bf4_playerstats_test`
- PostgreSQL writable primary
- Alembic: `0003_request_gates`
- resource/lane: `detailed/background`
- test soldier: `24`
- deliberately short test lease: `2s`
- collector A: `b2b3ef60-62e8-4d4a-91b0-41a2e2a3b001`
- collector B: `b2b3ef60-62e8-4d4a-91b0-41a2e2a3b002`

The harness used exact test-row cleanup and did not consume live Battlelog traffic.

## Initial ownership

Collector A claimed job `53` for soldier `24` as attempt `1` with lease token:

`1fdac07c-6f82-4c01-902c-979a436dde79`

The database row was `claimed` with lease expiry `2026-10-04 08:10:57.213029+00:00`.

Collector B attempted to claim before expiry and was correctly blocked.

## Post-expiry reclamation

After the deliberately short lease expired, collector B reclaimed the same logical job `53` for soldier `24` as attempt `2` with a new lease token:

`c9ab0e20-b433-4018-9a59-c50f350c90be`

Validated:

- same logical job: PASS
- attempt increment `1 -> 2`: PASS
- token A differs from token B: PASS
- ownership transferred to B: PASS

## Stale-owner fencing challenge

The retained stale ownership object from collector A was deliberately used against B's reclaimed job.

All state-changing stale operations were rejected:

- A attempted to mark B's job running: REJECTED
- A attempted to renew B's lease: REJECTED
- A attempted to release B's job: REJECTED
- A attempted to finalize B's job: REJECTED

After those attacks, B's current ownership remained intact: PASS.

B then successfully marked its reclaimed job running and finalized the current ownership.

## Final validation

- A initially owns token A: PASS
- B blocked before expiry: PASS
- B reclaims same job: PASS
- reclaim increments attempt: PASS
- reclaim rotates token: PASS
- all stale A mutations rejected: PASS
- B ownership survives stale attacks: PASS
- B can mark reclaimed job running: PASS
- B can finalize current ownership: PASS
- Battlelog requests: 0
- exact cleanup: PASS

Result: **BF4PS PHASE 3B LEASE EXPIRY / RECLAMATION / FENCING PROOF: PASS**

## Conclusion

Phase 3B demonstrates the failure mode the lease-token fencing design exists to handle. A collector may retain stale in-memory claim state after its lease expires, but once another collector reclaims that job under a new ownership tuple, the stale collector cannot mark, renew, release, or finalize the current owner's work.

This satisfies the frozen Phase 3B proof requirements. Per the frozen implementation order, the next stage is **Phase 3C — drain, stop, and restart behavior under concurrency**.
