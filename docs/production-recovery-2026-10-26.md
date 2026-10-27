# Production recovery and collector naming — 2026-10-26 (HST)

## Incident and recovery
- A large `equipment_rank_rows` table (~97 GiB, ~470 million rows at investigation) and ranking-generation garbage collection/autovacuum contributed heavy PostgreSQL WAL. The physical `mak-db-01` standby accumulated ~23 GiB replay backlog; disk I/O was the limiting factor.
- Paused ranking builders, ranking GC, player collectors, platoon scheduling, Discord HA, metrics sync and selected website services to let replay recover. **Exception discovered later:** `rnt-01` player collector was still running as `docker-collector-1`, so the fleet-wide stop by the `bf4ps-production-collector` name missed it.
- Expanded primary and standby storage, and brought 8 additional standby vCPUs online (16 total); neither alone proves the disk bottleneck is resolved.
- Replay reached 0 bytes. Restarted eight named player collectors, both Discord HA containers (`mak-01` leader, `rnt-01` standby), website `bf4ps-manual-api.service`, and both platoon alternating timers (`mak-05`, `hnl-03`). The ninth player collector on `rnt-01` had been running throughout. Latest observed replay gap after discovery: **0 bytes**. This is a point-in-time observation, not a sustained-load guarantee.
- Platoon scheduling resumed; `hnl-03` completed a soldier discovery, while `mak-05` reported `ValueError: Roster, personaBoxes and HTML card account IDs do not reconcile` on a roster job. Its retry mechanism reported a retry; investigate recurring failures rather than weakening parser validation.

## Nine player collector hosts
`mak-01`, `mak-02`, `mak-03`, `mak-04`, `hnl-01`, `hnl-02`, `hnl-03`, `kah-01`, `rnt-01`.

## rnt-01 naming correction
- Verified `rnt-01` collector was active, processing successful PC/PS4/Xbox profile/detailed/weapon/vehicle jobs, using image `bf4-player-stats:catalog-fix-installed-20261025` and restart policy `unless-stopped`.
- Renamed the live container with `docker rename docker-collector-1 bf4ps-production-collector` (no restart).
- Updated **deployed** Compose override `/opt/bf4ps-ranking-0016-deploy/override.yaml` to include `services.collector.container_name: bf4ps-production-collector`; backed up original as `override.yaml.pre-container-name-20261026`. This override also pins the currently deployed catalog-fix image; do not assume the repository's release-candidate image is equivalent.
- Updated repository `player-collector/deploy/docker/compose.yaml` to carry the consistent name for future deployments.
- **Operational rule:** fleet inventories and stop/start scripts must inspect all containers/Compose projects, not only name-matching containers. Verify every host and Docker Compose project before declaring a full fleet stop. A future Compose recreation must be tested for adoption/replacement behavior; changing a container name alone does not validate a future rollout.

## Remaining work and safety gates
- Ranking builder and ranking GC remain intentionally paused. The previously configured GC rate of 10 generations/minute is not safe to assume under the observed WAL/disk pressure. Reassess pacing, monitor `pg_stat_replication`, and stage changes before restarting.
- `public.equipment_rank_rows` autovacuum was **temporarily disabled** on the primary during recovery. **Restore autovacuum safely**, retaining/reassessing previous tuning `autovacuum_vacuum_scale_factor=0.02` and `autovacuum_vacuum_threshold=100000`, once the maintenance strategy and WAL budget are ready. Do not leave it disabled indefinitely.
- Weapon/vehicle metrics synchronization, discovery, scheduled website exports and platoon submission were still paused at this checkpoint. Manual refresh API process is active, but end-to-end refresh/security-gate behavior has not yet been verified.
- Do not confuse BF4PS with the separate BF4 ServerWatcher system on the same hosts.

## Replication check
On primary `mak-db-02`, as postgres:
```sql
SELECT application_name, state,
       pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn)) AS total_gap
FROM pg_stat_replication;
```
Track the trend over time and watch disk latency and free space, not just one zero-lag sample.
