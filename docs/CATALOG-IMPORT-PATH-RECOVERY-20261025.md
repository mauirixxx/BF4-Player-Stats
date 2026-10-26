# Catalog import-path correction and dossier recovery — 2026-10-25

## Root cause

The nine collector containers carried `bf4-player-stats:catalog-fix-7e94f8e`, whose optimized modules were placed in `/app/bf4ps/`. The production entrypoint is `python /app/scripts/bf4ps_production_collector.py`. Python resolved `bf4ps` from `/usr/local/lib/python3.12/site-packages/bf4ps/`, where the old per-item catalog upsert remained. The image tag alone did **not** establish that the hotfix was active.

The database showed the old `INSERT INTO weapon_catalog ... ON CONFLICT DO UPDATE` from hnl-03, hundreds of catalog updates per minute, advisory-lock queues, and approximately 1.05M weapon / 499k vehicle dead rows. The catalogs have only 174 and 82 live entries.

## Immediate production remediation

All nine running collector containers had the four optimized modules copied from `/app/bf4ps/` to their installed `site-packages/bf4ps/` directory and were restarted to reload Python modules. On hnl-03 the import path and optimized bulk persistence code were verified after restart. The change survives container restarts **but not container recreation**.

The reproducible `player-collector/deploy/docker/Dockerfile.catalog-installed-hotfix` creates `bf4-player-stats:catalog-fix-installed-20261025` from the existing local hotfix image and copies the optimized modules into the actual import path. The corrected image was built on all nine nodes; the running containers still reference the prior image tag, so **the corrected image must be explicitly selected in future standalone/Compose deployments**. Do not recreate a collector from the old tag without switching to the corrected image. Do not commit production environment files.

On mak-db-02 ordinary online `VACUUM (ANALYZE)` was run on both catalogs after restarting the workers. Concurrent index rebuild was initiated for `weapon_catalog_pkey`; verify completion and progress before scheduling further index maintenance. Do not use `VACUUM FULL` on production without a maintenance window.

## Soldier dossier query fix

`website/api/soldier_detail.py` now bounds the soldier weapon/vehicle rows to top 15 **before** joining catalog names. A previous explain showed the unbounded weapon-catalog join taking 7.44 seconds; after the query fix the same soldier-detail HTTP endpoint returned 200 in ~0.62 seconds. This is a read-path safeguard, not a substitute for fixing catalog churn.

## Verification and remaining work

- Verify all nine running collectors import `bf4ps.weapon_persistence` from site-packages and that its content uses the optimized bulk lookup.
- Verify catalog update counters over time, dead-tuple trends, autovacuum health, and absence of long-lived blocking transactions.
- Complete/verify concurrent index maintenance and measure index sizes and dossier response times.
- Recreate collectors from the corrected image using each host's existing deployment configuration and preserved environment; do not replace unrelated ranking/platoon services.
- Keep `docs/catalog-persistence-policy.md` authoritative for the bounded 15-minute refresh policy.


## Completed database maintenance verification

After terminating a single 11-hour idle-in-transaction backend that held an old snapshot, all four indexes were rebuilt using `REINDEX INDEX CONCURRENTLY`: `weapon_catalog_pkey`, `weapon_catalog_weapon_guid_key`, `vehicle_catalog_pkey`, and `vehicle_catalog_vehicle_guid_key`. All four commands returned `REINDEX`. PostgreSQL reported `n_dead_tup=0` for both catalogs after vacuum. Index sizes were 16 kB, 32 kB, 16 kB and 16 kB respectively, down from roughly 30 MB total. This is a point-in-time check, not proof that future catalog churn has stopped.


## Permanent nine-node image cutover — completed

All nine collectors now run `bf4-player-stats:catalog-fix-installed-20261025`, not the older tag. Eight standalone containers were recreated with their existing environment, host network, non-root user, command and `unless-stopped` restart policy preserved; old containers are retained as `bf4ps-production-collector-before-installed-fix-20261025` for rollback. On `rnt-01`, the Compose override `/opt/bf4ps-ranking-0016-deploy/override.yaml` was updated, backed up to `override.before-installed-catalog-20261025.yaml`, and only `collector` recreated. All nine reported running, zero restart counts, and successful post-cutover collection events across weapons, vehicles, detailed, and profile resources. PostgreSQL catalog update counters remained unchanged from the post-maintenance baseline (`weapon_catalog=3283048`, `vehicle_catalog=1547258`) at the verification check, with zero reported dead tuples in each catalog. Continue monitoring as a point-in-time observation.

The preceding warning that the running containers reference the old image is superseded by this completed cutover. The corrected Dockerfile is committed to `main`; for reproducible future deployment, build this overlay on each node's existing catalog hotfix image or publish a versioned image with the same installed-package correction. Avoid overwriting production collector environments.
