# BF4PS — first live multi-platform detailed cohort (2026-10-11)

**PASS — PC, PS4 and Xbox One now have verified real Battlelog detailed-statistics persistence in the isolated Stage 9C integration scratch DB. Production HOLD.**

## Environment

- Host: `tcou`.
- Database: `bf4ps_scratch_stage9c_integration`, role `bf4ps_stage9c_integration`, writable primary, Alembic `0004_stage9c_supervision_runs`.
- New runner: `scripts/stage9c_live_multiplatform_detailed.py`, commit `bea2976`.
- Preflight: exact DB identity, role, writable state, revision, empty job queue, single known collector and previously absent cohort soldiers.
- Existing background collector with database-coordinated admission, shared 10-second egress request interval, 120-second lease, 15-second HTTP timeout, 3600-second retry deferral.
- Max newly admitted detailed attempts: **2**. No automatic repeat after failures; no distributed fleet activation.

## Results

| Platform | Soldier | Persona | Rank | Kills | Deaths | History | Events | Jobs |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| PC (previous milestone) | mauirixxx | 236753552 | 140 | 256660 | 212302 | 1 | 2 attempt-start + 2 success | 0 |
| PS4 | xSilverMystx | 303498475 | 140 | 311649 | 206457 | 1 | attempt-start + success | 0 |
| Xbox One | S0UL OF STEEL | 928420744 | 124 | 19347 | 15068 | 1 | attempt-start + success | 0 |

The two new platform requests returned `CollectedJob` and `history_appended=True`. PS4 duration 637 ms, Xbox One duration 878 ms. New cohort completed in 11.47 seconds, exit code 0. Both new rows independently verified with `detailed_state=success`, `source_fetched_at`, one history row, two expected events and zero queued jobs.

## Next

Expand to a bounded multi-platform weapons and vehicles cohort, verify catalog sharing and per-soldier rows across platforms, then begin larger multi-soldier batches. Do not reuse the first-run script on these now-present identities. This is not yet a distributed production live soak or proof of all physical HTTP behaviors.
