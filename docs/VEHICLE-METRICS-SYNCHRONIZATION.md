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

## November 4, 2026 production incident

The MAK-01 weapon and MAK-02 vehicle metrics synchronization services were found **failed/stopped** (last activity October 26). Newly collected raw equipment statistics can therefore be absent from legacy indexed metrics. The repair scripts were updated to require production Alembic `0023_compact_exclusion_guard` and installed on their respective hosts with backups. This is a revision compatibility update, not proof of successful continuous reconciliation. The compact rank builder reads raw stats directly; the website equipment-position lookup and legacy leaderboard fallback use indexed metrics, so missing derived records can break dossier deep links. Vehicle 80 audit on November 4: 367,770 eligible raw vs 235,688 indexed, gap 132,082. Before re-enabling unattended services, verify a controlled repair finishes within the configured 120-second statement timeout, check WAL and replica replay, and confirm XBoomSki (persona 947734894) is present in PC and ALL rankings.
