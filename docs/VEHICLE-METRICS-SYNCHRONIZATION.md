# Vehicle leaderboard metrics synchronization

Production deployment: 2026-10-22 on MAK-02. The service `bf4ps-vehicle-metrics-sync.service` reconciles `soldier_vehicle_stats` into `vehicle_leaderboard_metrics`, updates platform equipment populations, and advances vehicle rank scope versions when derived metrics change. Source: `player-collector/scripts/repair_vehicle_leaderboard.py`, `player-collector/scripts/vehicle_metrics_sync.py`. Unit: `player-collector/deploy/systemd/bf4ps-vehicle-metrics-sync.service`.

Runs one vehicle per transaction, waits 60 seconds between cycles, and loops over the 82-item catalog indefinitely. Cursor persists at `/var/lib/bf4ps-vehicle-metrics-sync/last_vehicle_id`, writable by container UID/GID 65532. Single host only: do not enable another instance without distributed coordination. The service makes **no Battlelog requests** and is independent of the MAK-01 weapon reconciliation service.

Validated: standalone read-only audit for vehicle 1; production repair for vehicle 1 upserted 7,100 rows; systemd service then processed vehicle 2, upserting 75,294 rows and persisting cursor 2. Both completed successfully. Schema revision checked: `0018_distributed_rank_queue`.

Operations:
```bash
systemctl status bf4ps-vehicle-metrics-sync.service
docker logs --tail 40 bf4ps-vehicle-metrics-sync
cat /var/lib/bf4ps-vehicle-metrics-sync/last_vehicle_id
```

Caveats: eventual consistency (not per-collection synchronous); first full catalog pass not yet observed; stale/deleted/excluded historical rows are not deleted by the upsert. Monitor PostgreSQL query load and leaderboard API responsiveness during the first full pass. The worker requires a review after schema migrations.
