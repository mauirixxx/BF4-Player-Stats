# Phase 1 Live Multi-Platform Detailed Validation

This record supplements `docs/phase1-detailed-collector.md` and captures the live multi-platform acceptance run performed on `tcou` against `bf4_playerstats_test` on 2026-10-04.

## Preconditions

The cohort identities were already present naturally in the BF4PS discovery dataset; no synthetic soldier rows were inserted:

| Platform | Soldier | Persona ID | BF4PS soldier ID |
| --- | --- | ---: | ---: |
| PC | `mauirixxx` | 236753552 | 1 |
| PS4 | `xSilverMystx` | 303498475 | 8680 |
| Xbox One | `S0UL OF STEEL` | 928420744 | 49649 |

The branch passed 30 automated tests before the live run.

## Live cohort result

The reusable harness `scripts/phase1_multiplatform_cohort.py` executed one complete detailed-statistics collector invocation for each supported BF4PS platform through the real queue, fenced lease, PostgreSQL request gate, Battlelog detailed endpoint, normalizer, atomic persistence path, and queue finalization.

Observed results:

| Platform | Soldier | HTTP | Duration | History appended | History rows |
| --- | --- | ---: | ---: | --- | ---: |
| PC | `mauirixxx` | 200 | 719 ms | false | 1 |
| PS4 | `xSilverMystx` | 200 | 1008 ms | true | 1 |
| Xbox One | `S0UL OF STEEL` | 200 | 573 ms | true | 1 |

Selected normalized values were:

- PC: rank 140, time played 17,231,500 seconds, total score 163,074,106, kills 256,100, deaths 211,800.
- PS4: rank 140, time played 33,554,500 seconds, total score 235,406,205, kills 311,139, deaths 206,147.
- Xbox One: rank 124, time played 1,492,790 seconds, total score 18,578,544, kills 19,239, deaths 14,954.

Database validation reported all platforms successful and all three actionable queue jobs finalized. The temporary request-gate row and temporary collector-registry row were removed. Current statistics, history, collection state, and structured collection events were intentionally retained.

The unchanged PC recollection correctly produced `history_appended = false` and left history at one row, providing another live confirmation that canonical decimal comparison prevents poll-time-only duplicate history. The first PS4 and Xbox One detailed collections each appended exactly one initial history snapshot.

No unexplained HTTP 403 or throttle behavior occurred during this tiny cohort run.

## Acceptance consequence

This run satisfies the Phase 1 requirement that live Battlelog detailed JSON be fetched, normalized, and persisted through the complete collector path for all three supported platforms: PC (`platformInt=1`), PS4 (`platformInt=32`), and Xbox One (`platformInt=64`).

The next unresolved Phase 1 behavioral boundary is failure/retry handling: retryable collection failures must preserve last-known-good statistics, record structured failure state/events, release work for future eligibility, and remain protected by lease-token fencing. That behavior must be proven before converting the one-shot orchestration into a continuously running collector worker.