# Derived leaderboard ranking design (2026-10-18)

Status: design only; no schema change or backfill deployed.

Source: recovered Alembic 0001-0012; chain links validated on mak-01.

Raw collector weapon and vehicle persistence replaces all soldier equipment rows transactionally. Derived metrics must similarly replace rows and remove vanished equipment.

Weapon ranking: kills; KPM = kills*60/time_equipped_seconds when time>=60; accuracy = shots_hit*100/shots_fired when shots_fired>=100 and shots_hit<=shots_fired.

Vehicle ranking: canonical family SUM/MAX aggregation before KPM, using the audited website family mapping.

Proposed indexed read models: per-soldier per-weapon metrics and per-soldier per-canonical-vehicle metrics, each with kills and rate ordering indexes.

Preserve global tie ranks, population, percentile divisions, exclusions, search and pagination; only use bounded indexed reads for eligible first pages.

Rollout: scratch Alembic rehearsal; EXPLAIN benchmarks; migration and schema-doc update; bounded restartable PostgreSQL-only backfill; parity tests; transactional collector integration; feature-flagged API cutover; replication/WAL monitoring.

Never rescan Battlelog for backfill. Never apply speculative schema changes to production.
