# Historical testing and validation record

This document replaces one-off test harnesses and staging artifacts removed from the **consolidated distribution**. The original test source remains recoverable in Git history (before the cleanup commit) and historical branches. It is **not** evidence that all tests passed or that a clean installation has been validated.

## Recorded results

- Platoon collector: nine unit tests passed on the consolidation checkout (October 21, 2026), covering roster parsing, soldier discovery and claim fencing. Following the synchronized deployment of commit `24db633`, local available tests passed 4/4 on `mak-05` and 9/9 on `hnl-03`. All eleven deployed Python script hashes matched, and both systemd alternating timers were active.
- Python syntax audit: 129 Python files parsed without syntax errors in the consolidation checkout before cleanup.
- Website tests: initial unittest run reported 20 tests with one outdated soldier-detail assertion and nine errors, mainly missing dependencies or old paths. After correcting the old path and assertion, the run reported 20 tests and eight remaining errors. **No passing website suite is claimed.**
- Player collector: its test modules covered discovery, request gates, dispatch, pacing, retries, account resolution, persistence, Battlelog parsers and production scheduling. These were **not executed successfully as a complete suite** during consolidation because required dependencies/test tooling were unavailable.
- Earlier distributed soaks, concurrency rehearsals and production checkpoints are described in `docs/` and historical design/checkpoint records. Their results are historical and must not be treated as a fresh deployment certification.

## Removed from the deployable tree

The following test harnesses and staging-only artifacts were removed so a default clone focuses on operational source. Their original contents can be recovered from commit `ab9419c` or earlier repository history.

- `platoon-collector/scripts/staging_web.py`
- `platoon-collector/tests/shared_lease_race.py`
- `platoon-collector/tests/test_battlelog_platoon_roster.py`
- `platoon-collector/tests/test_claim_fencing.py`
- `platoon-collector/tests/test_platoon_discovery_parser.py`
- `platoon-collector/tests/verify_claim_sql.py`
- `player-collector/tests/test_account_resolution.py`
- `player-collector/tests/test_background_service.py`
- `player-collector/tests/test_battlelog_detailed.py`
- `player-collector/tests/test_battlelog_profile.py`
- `player-collector/tests/test_battlelog_vehicles.py`
- `player-collector/tests/test_battlelog_weapons.py`
- `player-collector/tests/test_bounded_feeder.py`
- `player-collector/tests/test_collection_jobs.py`
- `player-collector/tests/test_collector_runtime.py`
- `player-collector/tests/test_detailed_failure.py`
- `player-collector/tests/test_detailed_persistence.py`
- `player-collector/tests/test_discovery.py`
- `player-collector/tests/test_discovery_service.py`
- `player-collector/tests/test_physical_dispatch_gate.py`
- `player-collector/tests/test_physical_dispatch_postgres.py`
- `player-collector/tests/test_production_collector_control.py`
- `player-collector/tests/test_production_collector_daemon.py`
- `player-collector/tests/test_production_scheduler.py`
- `player-collector/tests/test_release_identity.py`
- `player-collector/tests/test_request_gate.py`
- `player-collector/tests/test_retry_policy.py`
- `player-collector/tests/test_single_node_runtime.py`
- `player-collector/tests/test_vehicle_collector.py`
- `player-collector/tests/test_vehicle_persistence.py`
- `player-collector/tests/test_weapon_persistence.py`
- `website/scripts/staging_web.py`
- `website/site/index-paginated-staging.html`
- `website/site/soldier-paginated-staging.html`
- `website/tests/homepage_http_smoke.py`
- `website/tests/homepage_paginated_adapter.test.js`
- `website/tests/homepage_rank_comparison.py`
- `website/tests/homepage_staging_runtime.test.js`
- `website/tests/manual_api_live_smoke.py`
- `website/tests/test_admin_console_api.py`
- `website/tests/test_admin_moderation_service.py`
- `website/tests/test_community_export.py`
- `website/tests/test_exclusion_admission_contract.py`
- `website/tests/test_exclusion_reader_contract.py`
- `website/tests/test_general_leaderboard.py`
- `website/tests/test_global_soldier_search.py`
- `website/tests/test_homepage_api_metric_compat.py`
- `website/tests/test_homepage_paginated_adapter.py`
- `website/tests/test_homepage_staging_contract.py`
- `website/tests/test_homepage_summary.py`
- `website/tests/test_manual_request_api.py`
- `website/tests/test_player_exclusion_migration.py`
- `website/tests/test_soldier_detail_contract.py`

## Required future verification

Before calling a clean clone production-ready: install dependencies on a clean host; exercise the component startup paths; rehearse Alembic `0001` through `0017` on an **isolated disposable database**; compare its catalog to the documented live schema; verify current website API behavior and deployed source parity; and confirm both platoon worker scripts remain hash-identical. Record actual results rather than inferring success from the existence of old tests.

Alembic migrations, deployment scripts, operational code and schema documentation were intentionally retained, including migrations with historical `stage` or `soak` names.
