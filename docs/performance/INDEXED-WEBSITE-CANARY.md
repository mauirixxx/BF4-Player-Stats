# Indexed equipment Top 10 website canary — NOT DEPLOYED

This feature branch contains a snapshot of the currently running, uncommitted `api/leaderboard_api.py` from tcou (2026-10-18), plus a new isolated `api/indexed_equipment_top10.py`. It is NOT a clean cherry-pick onto the tracked base; review the 159-line existing local website delta separately before merging. The original `/opt/bf4ps-website` worktree was not modified by this experiment.

`BF4PS_INDEXED_EQUIPMENT_READS=1` opts in to indexed first-page Top 10 only (`page=1`, `page_size=10`, no search, no division filter). All other requests keep the legacy path. Weapon metrics: kills/KPM/accuracy. Vehicle metrics: kills/KPM. Vehicle IDs canonicalize using the website family map. Queries read the proposed Alembic 0013 derived tables, preserve active `player_exclusions`, platform filters, deterministic soldier-ID tie breaking, global competition rank and division. Cached equipment keys include the flag value.

**DO NOT ENABLE** on the production database at Alembic 0012: derived tables do not exist. Also do not enable before fully populated and continuously maintained derived tables are verified. Flag defaults OFF.

Four offline mocked API-contract tests pass. No real 0013 SQL execution, actual exclusion table integration, independent legacy-vs-indexed HTTP parity, EXPLAIN/BUFFERS, full-sized population count cost, or concurrent load measurement has passed yet. Counting eligible population still requires a cohort count and is not yet proven cheap. A full staging rehearsal is required before any deployment or production migration.

Fallback: unset `BF4PS_INDEXED_EQUIPMENT_READS` or set to `0` and restart only the canary service when approved. Do not reset or overwrite the live website worktree.

## Scratch SQL verification checkpoint (2026-10-18)

On mak-01, the website canary code was loaded from commit ea0718e in a separate detached worktree and executed against isolated PG16 0013 scratch containing 10,000 copied soldiers. A scratch-only `public.player_exclusions(platform, persona_id, active)` table was created because the website-owned table is not part of collector migrations. Actual `leaderboard_api.get_page` legacy SQL and `indexed_equipment_top10.query_top10` SQL matched population and Top 10 soldier IDs, kills, KPM, accuracy, rank, position, and division in ten comparisons: weapon ID 5 kills/KPM/accuracy and vehicle family ID 1 kills/KPM, each on all and PC. Weapon ID 5 populations were 5,504 all and 4,575 PC; vehicle family ID 1 populations were 5,426 all and 4,496 PC. An active exclusion of the PC weapon leader (scratch transaction rolled back) changed both populations from 4,575 to 4,574 and promoted the same next soldier. These are successful limited real-SQL tests, NOT full coverage of all catalog items/platforms, HTTP deployment, query-plan benchmarking or production eligibility certification. No production writes or website deployment.
