# Phase 4C multiplatform sustained-run acceptance

Status: **PASS**

Phase 4C validated the existing detailed-stat collection lifecycle across all three supported BF4 platforms using the frozen 450-soldier cohort: 150 PC, 150 PS4, and 150 Xbox One.

## Frozen execution contract

- Cohort: 450 soldiers, exactly 150/150/150 across `pc`, `ps4`, and `xboxone`.
- Collectors: `phase3e-hnl-01`, `phase3e-kah-01`, and `phase3e-tcou`.
- Each collector contributed exactly 150 collection attempts.
- The run used the normal PostgreSQL-backed collection queue, collector ownership/lease lifecycle, and per-egress request gates.
- Phase 4C exercised only the `detailed` resource. Weapon and vehicle resources remain intentionally deferred to the next, more expensive collection phase.

## Corrected post-run reconciliation

The corrected read-only audit reconciled the complete attempt ledger:

- collection-attempt event span: `1805..2254`;
- exactly 450 collection attempts;
- 412 success events;
- 38 `temporary_failure` events;
- 0 `unavailable` events;
- 413 unique soldiers attempted;
- 0 HTTP 403 events;
- 0 HTTP 429 events;
- 0 throttle events;
- all three frozen collectors participated and owned no job at audit time.

The platform event distribution was:

| Platform | Attempt events | Success events | Temporary failures |
|---|---:|---:|---:|
| PC | 187 | 150 | 37 |
| PS4 | 150 | 150 | 0 |
| Xbox One | 113 | 112 | 1 |
| **Total** | **450** | **412** | **38** |

The apparent PC count above the 150-soldier cohort ceiling is expected. Thirty-seven PC soldiers first produced retryable normalization failures and later succeeded, so their retry attempts are separate attempt events for the same frozen identities. This is why 450 collection attempts represent 413 unique soldiers rather than 450 unique soldiers.

## Failure/recovery behavior

All 38 observed failures were `battlelog_normalization` temporary failures rather than transport throttling.

The 37 PC temporary failures recovered during the run and converged to `success` with detailed current/history persistence.

One Xbox One soldier remained unresolved at the acceptance boundary:

- soldier ID: `9392`;
- persona ID: `186705922`;
- name: `fubofam`;
- platform: `xboxone`;
- job ID: `2183`;
- event ID: `2232`;
- result: `temporary_failure`;
- error class: `battlelog_normalization`;
- error: `generalStats is missing or is not an object`.

The corresponding retry job remained `pending`, unowned, and lifecycle-valid. The corrected audit therefore treats that residual retry as expected evidence of the retry lifecycle rather than as queue corruption.

## Acceptance checks

The corrected Phase 4C audit passed all of the following:

- exactly 450 collection attempts recorded;
- one contiguous 450-event attempt span;
- lifecycle-valid attempt event/result shapes;
- event identity and platform match the frozen cohort;
- all three supported platforms exercised;
- no platform exceeds its 150-soldier success ceiling;
- collection state agrees with each soldier's latest attempt;
- every successful soldier has detailed current and history persistence;
- unresolved failed soldiers have no detailed current row;
- residual cohort jobs exactly match unresolved temporary failures;
- residual retry jobs are pending and unowned;
- zero foreign detailed jobs;
- zero 403/429 throttle events;
- exactly three frozen collectors participated;
- stable collector registry identities remain present;
- all frozen collectors own no current job.

Final audit result:

`PHASE 4C MULTIPLATFORM POST-RUN ACCEPTANCE: PASS`

## Conclusion

Phase 4C demonstrates that BF4PS can sustain distributed detailed-stat collection across PC, PS4, and Xbox One while preserving queue ownership, retry lifecycle, persistence, and shared outbound pacing. Malformed Battlelog payloads are isolated as retryable normalization failures and do not crash the workers or corrupt queue state.

With multiplatform detailed collection accepted, the next test boundary is the deliberately more expensive weapon/vehicle collection phase. That phase must be designed and preflighted separately because it exercises the `weapons` and `vehicles` resource state families and their catalog/per-soldier persistence tables rather than merely increasing the Phase 4C detailed-stat workload.
