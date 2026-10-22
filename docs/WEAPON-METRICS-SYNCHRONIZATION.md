# Weapon leaderboard metrics reconciliation

The raw source is `soldier_weapon_stats`. The website's bounded Top 10 reads `weapon_leaderboard_metrics`. These must be synchronized; the distributed rank generation worker does not itself populate missing metrics.

## Deployment (2026-10-22)

Single active reconciler on MAK-01: `bf4ps-weapon-metrics-sync.service`, running a separate Docker container. It does not change the existing distributed rank worker or request Battlelog data. Source: `player-collector/scripts/repair_weapon_leaderboard.py` and `player-collector/scripts/weapon_metrics_sync.py`. Unit: `player-collector/deploy/systemd/bf4ps-weapon-metrics-sync.service`.

Each successful transaction upserts changed/missing derived weapon metrics, updates the equipment population per platform and bumps ranking scope versions if metrics changed. One weapon per cycle, 60 seconds between starts, persistent cursor in `/var/lib/bf4ps-weapon-metrics-sync/last_weapon_id`. After the highest weapon ID, it wraps to the first. This is **eventual reconciliation**, not transactional real-time synchronization; one full pass over 174 catalog items takes several hours. Concurrent collector updates can arrive between a weapon's reconciliation and its next cycle.

The state directory must be writable by Docker UID/GID 65532:65532. Only one reconciler should run; do not enable the service on additional nodes without distributed mutual exclusion.

## Operations

```bash
systemctl status bf4ps-weapon-metrics-sync.service
docker logs --tail 40 bf4ps-weapon-metrics-sync
cat /var/lib/bf4ps-weapon-metrics-sync/last_weapon_id
```

For a single-weapon read-only audit, invoke `repair_weapon_leaderboard.py --weapon-id 42` using the collector image, host network, production env file, and mounted code. Add `--apply` only after validating the target. A verified targeted repair of weapon 42 restored soldier 13848 (24Mikemann24, 339707 kills) to the indexed leaderboard.

## Caveats and follow-ups

The synchronization worker currently covers **weapons only**, not vehicles. It is not a substitute for testing fresh collection-to-leaderboard latency, and it does not remove excluded or deleted historical metrics rows. The script checks the deployed schema revision `0018_distributed_rank_queue`; review it after migrations. Monitor DB load and rank-generation freshness during the full first pass. Production validation: weapon 42 repaired, then the service processed weapon 43, upserting 6,992 records and persisting cursor 43. The existing distributed ranking worker remained active.
