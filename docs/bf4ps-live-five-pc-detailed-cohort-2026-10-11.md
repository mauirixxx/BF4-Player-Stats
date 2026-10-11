# BF4PS — five additional live PC detailed collections (2026-10-11)

**PASS — five new PC soldiers successfully fetched from Battlelog and persisted through the real detailed collector. Production HOLD.**

## Environment and bounds

- Host `tcou`; DB `bf4ps_scratch_stage9c_integration`; writable role `bf4ps_stage9c_integration`; Alembic `0004_stage9c_supervision_runs`.
- Script `scripts/stage9c_live_five_pc_detailed.py`, commit `58d532f`.
- Five known PC identities selected from previously frozen Phase 4A cohort. Exact DB/role/revision, empty queue, known collector and absent soldier identities checked before writes.
- Five admitted attempts maximum; 10-second shared egress interval, 120-second lease, 15-second timeout, 3600-second retry deferral. No fleet activation.
- Five successful `CollectedJob` results, all `history_appended=True`; wall runtime 41.10 seconds, exit code 0.

| Soldier | Persona | Rank | Kills | Deaths | History | Events | Jobs |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| KamiPebble | 1462860155 | 14 | 222 | 385 | 1 | started + success | 0 |
| MANHUNT1999 | 1472714233 | 122 | 19724 | 12307 | 1 | started + success | 0 |
| HyperMaxZ | 1477654907 | 132 | 42584 | 31671 | 1 | started + success | 0 |
| LevchenkoBIKS | 1479243208 | 87 | 7837 | 10814 | 1 | started + success | 0 |
| Peruvian_Baker | 1563112811 | 140 | 297370 | 230199 | 1 | started + success | 0 |

All five `collection_state.detailed_state` fields are `success`; each has one `detailed_stats_history` row, two expected events and no remaining collection job.

Combined with previous milestones: **8 live soldiers have persisted detailed stats across PC, PS4 and Xbox One**. Three of them (one per platform) also have persisted weapons and vehicles.

## Next engineering gate

Replace one-off cohort scripts with a general bounded manifest-driven runner that supports dry-run, idempotent soldier registration, durable run accounting and restart-safe resumption. Validate full three-resource collection on the five new PC soldiers before widening the cohort. This run alone does not establish distributed production readiness.
