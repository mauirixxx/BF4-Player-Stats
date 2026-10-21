# BF4PS Phase 3C operator lifecycle validation

Status: **PASS — live test-database integration evidence**

Date: 2026-10-04 UTC

Phase 3 design reference: `docs/phase3-distributed-collector-design.md`

Current Alembic head: `0003_request_gates`

## Purpose

Preserve the deterministic Phase 3C proof that BF4PS operator drain/stop/restart semantics remain authoritative while another collector continues servicing the same shared queue.

Harness: `scripts/phase3c_operator_lifecycle_integration.py`

No Battlelog request was performed.

## Test boundary

- database: `bf4_playerstats_test`
- PostgreSQL writable primary
- Alembic: `0003_request_gates`
- resource/lane: `detailed/background`
- frozen soldiers: `25`, `26`, `27`
- collector A: `b2b3ef60-62e8-4d4a-91b0-41a2e2a3c001`
- collector B: `b2b3ef60-62e8-4d4a-91b0-41a2e2a3c002`
- exact test-row cleanup
- Battlelog requests: `0`

## Observed lifecycle

Collector A initially claimed soldier `25` as attempt 1.

The operator drain was then applied to A. A's heartbeat/control view observed the drain and A was blocked from claiming new work. Its already-owned job was not silently abandoned: A finalized that owned work successfully.

While A was drained, collector B continued independently and processed soldier `26`.

A was then cleanly stopped. Its registry heartbeat state became `unknown`.

A restarted using the same stable collector UUID and identity. Registration preserved the operator-owned control state:

- `enabled=True`
- `drained=True`

The restarted A remained blocked from claiming new work. Restart therefore did not act as permission to override the drain.

Only after an explicit operator undrain did A observe:

- `enabled=True`
- `drained=False`

A then safely rejoined the shared queue and processed soldier `27`.

## Final validation

- initial collectors enabled/undrained: PASS
- A drain visible through heartbeat: PASS
- drained A accepts no new work: PASS
- A gracefully finalizes owned work: PASS
- B continues while A drained: PASS
- A clean stop succeeds: PASS
- restart preserves same identity: PASS
- restart preserves drained control: PASS
- restarted drained A still blocked: PASS
- explicit undrain enables A: PASS
- A safely rejoins and finalizes: PASS
- all frozen jobs finalized: PASS
- collector rows remain distinct: PASS
- Battlelog requests: 0
- exact cleanup: PASS

Result: **BF4PS PHASE 3C OPERATOR LIFECYCLE PROOF: PASS**

## Conclusion

Phase 3C satisfies the frozen Phase 3 operator-lifecycle proof. A deliberate drain is distinct from failure/heartbeat loss: it prevents new claims while allowing already-owned work to complete. Another collector continues independently. Stop/restart preserves A's stable identity and, critically, preserves the operator's drained state. A cannot resume work merely because its process restarted; an explicit undrain is required.

With retained PASS evidence for Phase 3A, Phase 3B, and Phase 3C, the frozen Phase 3 design now permits entry into **Phase 3D — two-host distributed proof**.
