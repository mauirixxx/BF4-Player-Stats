# BF4PS — v1.0.0 consolidation and 1,800-new-soldier soak plan

Status: **DESIGN/PREFLIGHT ONLY — NOT IGNITED**
Date: 2026-10-12 HST
Authority: existing documented schema `docs/database-schema-reference.md`, migrations, and the milestone evidence. The test must use the scratch database `bf4ps_scratch_stage9c_d3`, never the production BF4SW database.

## Preserve baseline
Keep the 451 fully successful soldiers (151 PC, 150 PS4, 150 Xbox One) and their history. Preserve 399 historical profile and one weapon failure event. Snapshot or back up the scratch DB before cohort seeding; do not reset it.

## New cohort contract
Add **1,800 genuinely new** BF4 soldier identities: 600 PC, 600 PS4, 600 Xbox One. The intended post-seed total is 2,251 (751 PC, 750 PS4, 750 Xbox One). Select from the existing BF4SW alias source using **read-only** source credentials. Do not fabricate persona IDs. Deduplicate on `(platform, persona_id)` against the scratch database and within the proposed cohort. Freeze a manifest with platform, persona ID, source name, and imported soldier ID before allowing collection.

The current `three_site_450_ramp.py` **cannot** be reused unchanged: it asserts 450 Phase4C IDs and limits collection to them. A new bounded harness and explicit allowlist are required. Keep the three existing worker egress identities and shared request gate unchanged.

## Before any writes or traffic
1. Verify schema against documented Alembic head and live database introspection.
2. Confirm source read-only credentials are available and count 600+ unique, non-overlapping identities on each platform.
3. Confirm scratch DB backup and available PostgreSQL storage; document restore path.
4. Verify workers are on identical source hashes and have passing tests.
5. Freeze new 1,800-persona manifest and expected 7,200 four-resource successes; the 451 prior successes do not count toward new-cohort acceptance.
6. Specify bounded request ceiling **with retry headroom** and elapsed-time envelope. With a 5-second shared request spacing, 7,200 attempts alone imply at least 10 hours if truly globally serialized; verify actual gate semantics before scheduling.
7. Disable automatic unrelated discovery/scheduling for this bounded experiment and verify the only eligible jobs belong to the new cohort.
8. Test dry-run and rollback paths before ignition.

## Soak and acceptance
Measure by platform, resource, worker, and error class. Success means 1,800/1,800 new soldiers with all four resources persisted, no duplicate identity rows, no orphan jobs, no unresolved state, and zero unexpected throttle signals. Retain retry events as evidence. Exercise graceful drain/restart and one worker loss/reclaim after confirming lease safety. Include a several-hour unattended window; if completion needs longer, do not truncate the test simply to meet a nominal duration.

## Documentation and release packaging
Maintain `docs/PROJECT-CURRENT-STATE.md` as historical index once retrieved from its GitHub commit; append this milestone and subsequent 1,800 acceptance evidence. Preserve `docs/database-schema-reference.md`, migrations, collector architecture, BF4SW discovery contract, production scheduling and operational runbook, and phase acceptance evidence. Archive old experiments in Git rather than including them in the production Docker image.

Docker release packaging follows the systemd soak, but must receive its **own** clean install/migration/restart validation before v1.0.0. No database credentials in the image or Git history. The six stale daemon-test assertions were updated and 430/430 tests passed on tcou; this does not substitute for multi-node binary/source hash parity or live soak.

## Current status
- 451-soldier four-resource milestone: PASS.
- Temporary raw-HTML capture: removed on all three nodes; 30 files deleted.
- 1,800-new-soldier cohort: **not selected, seeded, or started**.
- Git consolidation, branch cleanup, and Docker packaging: pending.
