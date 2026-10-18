# Indexed equipment rankings — implementation checkpoint

2026-10-18: Operator completed clean Alembic 0001–0012 scratch rehearsal, confirmed `0012_manual_verify_api` and 27 public tables. Scratch container was disposable and removed.

Feature branch adds **proposed** 0013 migration for inert derived read-model tables and five ordering indexes. No production schema or data changes. Before applying anywhere: rehearse 0013 on clean scratch, validate canonical vehicle families and all eligibility rules, implement bounded resumable backfill and transactional collector maintenance, verify exact Top 10/50 identities, score, rank, position and population, then feature-flag the API fast path. Preserve existing full-cohort pagination/search/division behavior.

Real-data microbenchmark from commit `6a06863` showed five exact individual-item Top 10 identity/score checks passing; those timings did not include eligibility or vehicle-family aggregation and do not prove live website response times.

Update: 0013 clean scratch upgrade, downgrade, re-upgrade passed on mak-01 (exit code 0, ~7 seconds), all five indexes verified; disposable container stopped. Added bounded, restartable, idempotent-by-window backfill implementation with production guard. **No scratch data fixture or full parity verification yet. Do not deploy.**

Scratch integration result: 0013 migrated fresh PostgreSQL 16; `scripts/performance/test_ranking_backfill.py` PASSED after fixing fixture identity inserts with `OVERRIDING SYSTEM VALUE`. Verified weapon KPM/accuracy eligibility thresholds, canonical vehicle SUM/MAX examples, null KPM, deterministic fixture ordering, bounded window reruns, and collection-state exclusion. This is a small synthetic fixture, **not full production leaderboard parity**. Scratch container stopped. Collector maintenance and API fast-path remain outstanding.

Collector wiring prototype: weapon and vehicle success paths now optionally refresh only their own derived metrics **inside the existing successful collection transaction**, behind `BF4PS_RANKING_DERIVED_WRITES=1` (unset by default). This is NOT enabled or deployed; production remains at 0012 and must not enable the flag. No full live-data parity or collector transaction rollback/concurrency test has been completed. Do not activate until those gates pass. The backfill also must not race live collector refreshes without coordination.
