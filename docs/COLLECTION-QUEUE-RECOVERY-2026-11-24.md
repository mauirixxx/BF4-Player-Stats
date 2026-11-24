# BF4PS collection queue starvation recovery — 2026-11-24 UTC

## Root cause and observed impact

Ten collectors continued heartbeating while collection stopped progressing. Before recovery, the queue held one running detailed job, no weapon/vehicle jobs, and 1,989 pending profile retries (only six eligible). `collection_state` held approximately 3.69 million never-attempted detailed, weapons and vehicle records. BF4SW discovery remained operational, but its `--materialize-production-jobs` option was **not enabled** in systemd; the production scheduler's default is off. The Phase 2 bounded feeder existed in source but was not running as a recurring production service. Discovery and queue replenishment are separate responsibilities.

## Deployed correction

On `tcou`, discovery now has systemd drop-in `20-materialization.conf`, enabling BF4SW observation-driven job creation with cutover `2026-11-24T01:00:00+00:00`. The separate `bf4ps-queue-feeder.timer` runs `player-collector/scripts/bf4ps_queue_feeder.py` approximately every 30 seconds, maintaining a **bounded** target of 240 immediately actionable background jobs, inserting at most 80 jobs per run and at most 20 per resource (detailed, weapons, vehicles, profile). It skips active `player_exclusions`, never-attempted states only, and existing jobs, with an advisory transaction lock and `0027_soldier_ban_status` revision gate. This deliberately does **not** enqueue the entire historical backlog at once. It uses the existing physical request gate and collectors for Battlelog traffic.

On `mak-01`, the existing Discord watchdog was extended with `collection:queue`. It uses the existing collector container's database connection for a read-only probe; it alerts after three unhealthy runs when fewer than five actionable jobs exist and no successful detailed/weapon/vehicle collection has occurred for 15 minutes. It sends a recovery notification through the same existing Discord channel/DM mechanism. No new Discord credentials are needed.

## Platoon ingestion verification

The live platoon worker on `mak-05` uses `/opt/bf4ps-platoon/scripts/platoon_queue_worker.py`, which invokes `admit_platoon_soldiers.py` after roster collection. That script **already inserts all four resource jobs** (`detailed`, `profile`, `weapons`, `vehicles`) for **newly inserted** soldiers from `platoon_roster_personas`, after checking the exclusion guard. It does **not** create jobs for roster soldiers that already exist in `soldiers` because its `_platoon_new_soldiers` temporary table contains only `INSERT ... RETURNING` identities. That is intentional for idempotent new-soldier bootstrap, but means platoon discovery is not an independent refresh scheduler for existing soldiers. The continuous feeder covers never-attempted existing soldiers. Platoon service source on `mak-05` has local modifications not present in its clean Git checkout; preserve and reconcile those before editing/deploying that worker. No platoon worker code was modified during this recovery.

## Operations

Check `systemctl status bf4ps-discovery.service bf4ps-queue-feeder.timer` and `journalctl -u bf4ps-queue-feeder.service -n 30` on `tcou`; inspect `collection_jobs` actionable depth and `collection_state` last success times using the verified schema. Check `bf4ps-watchdog.timer` and `collection:queue` on `mak-01`. The feeder is independently disableable with `systemctl disable --now bf4ps-queue-feeder.timer`. The discovery flag can be rolled back by removing its `20-materialization.conf` drop-in and restarting discovery. Preserve all existing collection retries and leases.
