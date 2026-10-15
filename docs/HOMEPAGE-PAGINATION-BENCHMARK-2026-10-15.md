# Homepage pagination: first live read-only benchmark (2026-10-15)

Feature branch: `feature/homepage-paginated-data`. No production website/API cutover yet.

## Conditions

- Executed on tcou against the production `bf4_playerstats` database using existing website database credentials.
- Every query was in a read-only transaction with `SET LOCAL statement_timeout = '5000ms'`.
- First implementation exceeded 5-second timeout for `kills/all`, because it joined the latest profile for every soldier before ranking/pagination.
- Refactored query obtains profile metadata **only for the selected 50 rows**.
- Results vary as collectors add data. These are individual samples, not p95 latency measurements.

| Metric | Platform | Page | Search | Division | Seconds | Population | Matched | Returned |
|---|---|---:|---|---:|---:|---:|---:|---:|
| kills | all | 1 | - | 0 | 0.287 | 25,042 | 25,042 | 50 |
| kills | pc | 2 | - | 0 | 0.290 | 19,636 | 19,636 | 50 |
| total_score | all | 1 | - | 0 | 0.294 | 25,042 | 25,042 | 50 |
| kills | all | 1 | cherch1 | 0 | 0.817 | 25,042 | 0 | 0 |
| kills | all | 1 | - | 1 | 0.371 | 25,042 | 751 | 50 |
| time_played_seconds | ps4 | 1 | - | 0 | 0.246 | 2,400 | 2,400 | 50 |

## Open validation before deployment

- The `cherch1` alias search returned zero in this *detailed-stats-only* cohort. Check identity and detailed-stat eligibility before declaring alias search broken. Global search must include soldiers without detailed stats.
- Confirm tie rank/division, zero/null values, score and playtime ordering, platform names, profile flags, and deep links against the existing frontend.
- Confirm exact metric allowlist matches the current homepage selector and authoritative schema.
- Benchmark repeated requests under representative concurrent collector load, including p50/p95 and cold-cache behavior.
- Integrate the endpoint into the existing API and add a lightweight global search endpoint without breaking equipment leaderboard endpoints.
- Replace giant JSON homepage loading only after full end-to-end comparison and rollback plan.
