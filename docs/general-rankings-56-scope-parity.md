# General ranking 56-scope parity run (2026-11-16)

Status: **IN PROGRESS**, not a completed 56-scope certification.

The isolated RNT-01 scratch harness is `player-collector/tests/scratch_general_rank_56_scope_parity.py`.
It requires `bf4ps_rank_scratch` with Alembic `0026_general_rank_snapshots` and explicitly refuses other database names/revisions. It publishes each of the 14 metric × 4 platform scopes, then compares snapshot and legacy JSON for four cases: default, division 1, page 100, and name search `bench_999`. It excludes only the intentionally new `published_at` and `generation_id` metadata from comparison. It fails immediately on a difference.

**Warning:** This is a mutating, potentially long-running scratch-only test. It inserts full generations and advances publication pointers. Do not run against production, and do not run concurrently with scratch retention experiments. It does not test live production data or replica lag.

Initial progress: kills/all passed (generation 9, population 560,000, 19.71 seconds); kills/pc passed (generation 10, population 186,666, 8.36 seconds). Remaining scopes and final outcome must be recorded from the actual process output. Do not report a full pass before the run finishes.
