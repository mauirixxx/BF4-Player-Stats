# BF4PS — Three-site post-HTTP abandonment and recovery (2026-10-11)

**FULL PASS — verified against live isolated D2 PostgreSQL.**

## Scope
- Database: `bf4ps_scratch_stage9c_d2` on `mak-db-02`, role `bf4ps_stage9c_d2`, revision `0005_stage9c_dispatch_ledger`.
- Nodes: `tcou` (prepare, stale-write test, final verify), `kah-01` (abandoned HTTP response), `hnl-01` (lease takeover and successful collection).
- Harness: `scripts/stage9c_three_site_post_http_abandonment.py` (commit `11662e0`).
- Starting event ID: 106. Job 600, soldier 565. Physical attempt ceiling: two.

## Observed execution
1. `tcou` prepared detailed refresh job 600.
2. `kah-01` claimed attempt 1, durably recorded physical request start (event 107), fetched real Battlelog detailed stats, normalized 48 fields, then deliberately abandoned the response before persistence.
3. Read-only database inspection confirmed job 600 remained `running` with expired lease and event 107 persisted.
4. `hnl-01` reclaimed the job and performed a second real HTTP request. Result: `RESCUE PASS CollectedJob(job_id=600, soldier_id=565, persona_id=1568678842, platform='pc', history_appended=False, duration_ms=644)`.
5. `tcou` attempted `persist_detailed_success` using the original Kahului attempt's lease token; PostgreSQL rejected it: `STALE PERSISTENCE REJECTED PASS`.
6. Final read-only `verify` on `tcou` completed:
   `VERIFY events=[('collection_attempt_started', UUID('1c3df74c-40ce-5e3b-bbc8-76775b46f4f7'), 1), ('collection_attempt_started', UUID('cc7473e9-76d9-518f-922f-7c38c9a80dd2'), 2), ('collection_success', UUID('cc7473e9-76d9-518f-922f-7c38c9a80dd2'), 2)] jobs=0`
   `POST-HTTP ABANDONMENT LIVE PASS`.

## Interpretation and boundaries
A previously completed Battlelog response was intentionally abandoned before persistence, not interrupted mid-socket. A different physical node recovered after lease expiry. The stale worker's database persistence was fenced out. Two real HTTP requests occurred, as expected for at-least-once external requests; the database accepted only the successful replacement owner's result. No additional detailed history row was needed because stats were unchanged (`history_appended=False`).

The test is **not** a mid-socket kill test or a multi-hour soak. No production BF4SW changes; production deployment remains HOLD.
