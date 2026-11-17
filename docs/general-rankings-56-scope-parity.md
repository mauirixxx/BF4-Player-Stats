# General ranking 56-scope parity run (2026-11-16)

Status: **IN PROGRESS**, not a completed 56-scope certification.

The isolated RNT-01 scratch harness is `player-collector/tests/scratch_general_rank_56_scope_parity.py`.
It requires `bf4ps_rank_scratch` with Alembic `0026_general_rank_snapshots` and explicitly refuses other database names/revisions. It publishes each of the 14 metric × 4 platform scopes, then compares snapshot and legacy JSON for four cases: default, division 1, page 100, and name search `bench_999`. It excludes only the intentionally new `published_at` and `generation_id` metadata from comparison. It fails immediately on a difference.

**Warning:** This is a mutating, potentially long-running scratch-only test. It inserts full generations and advances publication pointers. Do not run against production, and do not run concurrently with scratch retention experiments. It does not test live production data or replica lag.

Initial progress: kills/all passed (generation 9, population 560,000, 19.71 seconds); kills/pc passed (generation 10, population 186,666, 8.36 seconds). Remaining scopes and final outcome must be recorded from the actual process output. Do not report a full pass before the run finishes.

## Completed run results — 2026-11-16

**Result: ALL 56/56 scopes passed, process exit code 0, total runtime 152.31 seconds.**
Every scope compared four cases (default, division 1, page 100, and `bench_999` name search) with the existing legacy reader, excluding only the two intentionally new snapshot metadata keys.

**Important coverage limitation:** 12 scopes were populated: kills, wins, and time_played_seconds on each of all/pc/ps4/xboxone. Their all-platform populations were 560,000; pc 186,666; ps4 186,668; xboxone 186,666. The other 44 scopes had population ZERO because this synthetic fixture did not populate the other 11 metrics. These 44 cases prove empty-scope behavior, not nonempty ranking parity for those metrics. Populate a representative fixture for all metrics and repeat before claiming complete production-data parity.

First generation was 9 (kills/all); last generation 64 (chain_link_score/xboxone). The test advanced scratch publication pointers and created 56 generations. No production database or website configuration was changed. Scratch retention must be planned before repeated runs to avoid unbounded storage growth.

## UPDATE — all 44 previously empty scopes tested with populated data

The guarded scratch harness `player-collector/tests/scratch_general_rank_populated_parity.py` seeded 1,200 synthetic `detailed_stats_current` rows with values for all 11 previously empty metrics, using deterministic modulo scores to include ties and zero values. It then published each of the 44 affected metric/platform scopes and compared the new reader to the legacy reader for default, division 1, page 2 (20 rows), and name search. Every scope had nonzero population: all=1,200; pc=399; ps4=401; xboxone=400.

**Result: 44/44 PASS, exit code 0, runtime 16.15 seconds.** The earlier 12 populated scopes plus these 44 establish populated-data functional parity across all 56 combinations, with the important qualification that the other 44 scopes were tested on smaller cohorts. This is not a production load or replication benchmark. The harness mutates scratch fixture statistics and creates new published generations. Do not run it against production.
