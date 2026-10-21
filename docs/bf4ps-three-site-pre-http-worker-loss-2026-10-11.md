# BF4PS — first real three-site pre-HTTP worker-loss takeover (2026-10-11)

**PASS**: PostgreSQL lease expiry and another physical site's successful reclaim of the same job.

- Nodes: `tcou` (prepare/verify), `kah-01` (simulated worker loss), `hnl-01` (rescue).
- Shared writable isolated database: `bf4ps_scratch_stage9c_d2` on `mak-db-02.bf4statusbot.com`, role `bf4ps_stage9c_d2`, revision `0005_stage9c_dispatch_ledger`.
- Harness: `scripts/stage9c_three_site_pre_http_failover.py`; event baseline 104, global maximum two attempts, 8-second first lease.
- `tcou` prepared one detailed refresh job `job_id=598`, `soldier_id=565`.
- `kah-01` atomically claimed job #598 (attempt 1), marked it running and **exited intentionally before request-gate reservation, attempt-start event, or HTTP**. No process kill or crash during HTTP was used.
- `hnl-01` first tried to rescue while the lease was still valid. The harness refused with `expired=False` and sent no request.
- After lease expiry, `hnl-01` reclaimed job #598, executed one real Battlelog detailed refresh and persisted it successfully: `CollectedJob(job_id=598, soldier_id=565, persona_id=1568678842, platform='pc', history_appended=False, duration_ms=672)`.
- Final verification on `tcou`: only two post-baseline events, `collection_attempt_started` and `collection_success`, both attributed to the Honolulu collector UUID and `attempt_number=2`; `jobs=0`. `PRE-HTTP WORKER LOSS LIVE PASS`.

**Interpretation:** Durable queue lease expiry and takeover worked across real physical sites, with no duplicate HTTP in this controlled pre-HTTP exit scenario. This is **not** a proof of crash recovery during/after an ambiguous HTTP request, stale owner trying to finalize after takeover, or automated long-running failure detection. Production BF4SW untouched and production deployment remains HOLD.
