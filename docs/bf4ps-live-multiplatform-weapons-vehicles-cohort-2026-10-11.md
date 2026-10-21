# BF4PS — live cross-platform weapon and vehicle cohort (2026-10-11)

**PASS — all three platform families have live detailed, weapon and vehicle stats persisted in the isolated Stage 9C integration database. Production remains HOLD.**

## Environment and bounds

- Host `tcou`, DB `bf4ps_scratch_stage9c_integration`, role `bf4ps_stage9c_integration`, writable primary, revision `0004_stage9c_supervision_runs`.
- Script `scripts/stage9c_live_multiplatform_resources.py`, commit `2b2360e`.
- Cohort: PS4 persona `303498475` (`xSilverMystx`), Xbox One persona `928420744` (`S0UL OF STEEL`), each already proven via detailed-stat persistence.
- Existing single known collector and normal background production admission, 10-second shared egress request interval, 120-second lease, 30-second HTTP timeout, 3600-second retry deferral.
- Four attempted requests maximum (2 soldiers × 2 resources), no automatic repeat or fleet activation. Preflight refused wrong database/revision, nonempty queue, unknown collector, non-pristine resource state.

## Live results

| Platform | Resource | Soldier rows | Response bytes | Duration (ms) | Events | Jobs |
| --- | --- | ---: | ---: | ---: | --- | ---: |
| PS4 | weapons | 174 | 588201 | 2519 | started + success | 0 |
| Xbox One | weapons | 173 | 582428 | 978 | started + success | 0 |
| PS4 | vehicles | 82 | 453706 | 762 | started + success | 0 |
| Xbox One | vehicles | 82 | 452797 | 809 | started + success | 0 |

All four resource states `success`; process exit 0; wall runtime 31.48 seconds.

## Catalog reconciliation

- Shared `weapon_catalog` **174 before / 174 after**.
- Shared `vehicle_catalog` **82 before / 82 after**.
- Existing PC soldier has 174 weapon and 82 vehicle rows.
- New PS4 soldier has 174 weapon and 82 vehicle rows.
- New Xbox soldier has 173 weapon and 82 vehicle rows.

Catalog GUID identities were reused rather than duplicated. This is expected: one catalog identity can belong to many per-soldier stat records. Individual platform collections may have different row counts.

## Interpretation and next gate

All three BF4 platform families now have independently confirmed real Battlelog detailed/weapon/vehicle fetch, normalization and durable PostgreSQL writes. This validates **nine resource/platform combinations** across three soldiers; it is not yet a large cohort or distributed live soak. Next build an explicitly bounded repeatable multi-soldier cohort with idempotent setup, per-resource outcomes and durable global attempt accounting; then increase batch size without network/gateway redesign. Production HOLD remains unchanged.
