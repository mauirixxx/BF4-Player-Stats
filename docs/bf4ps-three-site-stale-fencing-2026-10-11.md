# BF4PS — real three-site stale-worker lease fencing (2026-10-11)

**PASS.** PostgreSQL rejected four stale-owner mutations after a different physical site reclaimed the job.

- Shared writable isolated D2 database: `bf4ps_scratch_stage9c_d2`, user `bf4ps_stage9c_d2`, revision `0005_stage9c_dispatch_ledger`.
- Nodes: `tcou` (prepare, fence, verify), `kah-01` (original owner), `hnl-01` (replacement owner).
- Script: `scripts/stage9c_three_site_stale_fencing.py`, initial commit `c7c1072`.
- Starting event ID 106; no queued jobs.
- Prepared detailed refresh `job_id=599`, `soldier_id=565`.
- Kahului claimed and marked running attempt 1 with an eight-second lease; no HTTP or attempt event.
- Honolulu initially refused takeover while `expired=False`, then successfully reclaimed job 599 as attempt 2 after lease expiry.
- tcou constructed a stale `ClaimedJob` with original Kahului collector UUID and a non-current token, then tested the actual queue primitives against the live PostgreSQL row:
  `renew_lease=False`, `release_for_retry=False`, `finalize_owned_job=False`, `mark_job_running=False`.
- Verified replacement row still had Honolulu collector UUID, current token, `running` status, and attempt count 2.
- Honolulu finalized the replacement-owned job using its valid token. Final tcou verification: `STALE FENCING INTEGRATION PASS`, zero jobs and zero new collection events.

## Boundaries

This proves queue ownership-token fencing across real sites and actual PostgreSQL operations. It does not test the full detailed-statistics persistence transaction, an HTTP request in flight during crash, or ambiguous HTTP completion. No real Battlelog requests were issued in this test. Production BF4SW was not modified; production rollout remains HOLD.
