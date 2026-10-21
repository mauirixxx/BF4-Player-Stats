# BF4PS — first live three-site dynamic queue claim (2026-10-11)

**PASS: 9/9 real Battlelog detailed refreshes, no per-node soldier assignment.**

- Nodes: `tcou`, `kah-01`, `hnl-01`.
- Shared isolated DB: `bf4ps_scratch_stage9c_d2` on `mak-db-02.bf4statusbot.com`; role `bf4ps_stage9c_d2`; Alembic revision `0005_stage9c_dispatch_ledger`.
- Script: `scripts/stage9c_three_site_dynamic_live.py`; GitHub commit `6e2f49a`.
- Nine existing successfully collected PC soldiers were re-enqueued for detailed refresh. Unlike prior tests, each collector received the **same allowed nine-soldier cohort**; no fixed soldier/node partition. Each worker was bounded to three successful claims, with global ceiling nine attempts, event baseline 86, and production background admission.
- All three processes ran concurrently and exited 0:
  - `tcou`: 3 successful claims, runtime 21.09 seconds
  - `kah-01`: 3 successful claims, runtime 22.13 seconds
  - `hnl-01`: 3 successful claims, runtime 22.26 seconds
- `tcou` final verification output:
  `DYNAMIC VERIFY counts={'tcou': 3, 'kah-01': 3, 'hnl-01': 3} events=18 outstanding=0`
  `THREE-SITE DYNAMIC LIVE PASS`
- Every soldier had exactly one new attempt-start and one new success event attributed to the same registered collector. No duplicate attempts or pending jobs. Every `CollectedJob` returned `history_appended=False`, confirming unchanged payload dedup.

## Interpretation

This proves three physically distinct live workers can dynamically claim different soldiers from the same PostgreSQL queue under an atomic bounded-attempt budget, with successful persistence and correct collector attribution. It does **not** yet prove failover after an actual worker crash, stale-lease recovery, a long-running live service, or balanced fairness under large uneven workloads. Production remains HOLD; BF4 Server Watcher production was not modified.
